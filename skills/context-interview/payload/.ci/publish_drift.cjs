// Called only by the trusted context-drift workflow. No secrets or API responses
// are written into reports. GitHub REST operations are injected for offline tests.
// API contract: https://docs.github.com/en/rest/git/trees#create-a-tree
// https://docs.github.com/en/rest/git/refs#update-a-reference
module.exports = async function publishDrift({github, context, core, payload, artifactUrl}) {
  if (payload.version !== 1 || !/^(?:[a-f0-9]{20}|unchecked)$/.test(payload.batch) ||
      !/^[a-f0-9]{40,64}$/.test(payload.baseSha) || !Array.isArray(payload.edits) ||
      ![undefined, 'seed-regrade'].includes(payload.purpose)) {
    throw new Error('Invalid checked drift publication payload');
  }
  const {owner, repo} = context.repo;
  const common = {owner, repo};
  const regrade = payload.purpose === 'seed-regrade';
  const label = regrade ? 'seed-regrade' : 'context-drift';
  const branch = `nodal/${label}-${payload.batch}`;
  const marker = `<!-- nodal-${label}:${payload.batch} -->`;
  const title = regrade ? `Restore freshly checked seeds (${payload.batch})` :
    payload.batch === 'unchecked' ? 'Context drift: lineage sources unchecked' : `Review context drift (${payload.batch})`;
  const base = payload.baseSha;
  const heading = `Nodal ${regrade ? 'seed re-grade' : 'context drift'} ${payload.batch}\n\nNodal-Base: `;
  const runUrl = `${context.serverUrl || 'https://github.com'}/${owner}/${repo}/actions/runs/${context.runId}`;
  const artifact = artifactUrl || runUrl;
  const suffix = `\n\n[Complete affected list and status patch](${artifact}).\n[Workflow run](${runUrl}).\n${marker}`;
  // GitHub has a 65,536-character body limit. The complete patch/list is retained
  // in the explicitly scoped artifact, not silently discarded when too long.
  function body(state, includePatch = false) {
    let text = `${state}\n\n${payload.report}`;
    if (includePatch && payload.patch) {
      let longest = 2;
      for (const match of payload.patch.matchAll(/`+/g)) longest = Math.max(longest, match[0].length);
      const fence = '`'.repeat(longest + 1);
      text += `\n\n${fence}diff\n${payload.patch}\n${fence}`;
    }
    if (text.length + suffix.length > 60000) {
      text = `${state}\n\n${payload.report.slice(0, 45000)}\n\nFull report and patch are in the linked artifact; this preview is abbreviated.`;
    }
    return text + suffix;
  }
  async function ref(name) {
    try { return (await github.rest.git.getRef({...common, ref: `heads/${name}`})).data.object.sha; }
    catch (error) { if (error.status === 404) return null; throw error; }
  }
  async function fallback(category, branchExists = false) {
    const state = `Status changes have not been applied to the default branch. Publication requires review (${category}).` +
      (branchExists ? ` An unmerged proposal branch may exist: \`${branch}\`; it has not been merged or reset.` : ' The patch below has not been applied to the default branch; check the workflow for any partial proposal-branch creation.');
    try {
    const issues = await github.paginate(github.rest.issues.listForRepo, {...common, state: 'open', per_page: 100});
    const existing = issues.find(issue => !issue.pull_request && (issue.body || '').includes(marker));
    const args = {...common, title, body: body(state, true)};
    const issue = existing ? await github.rest.issues.update({...args, issue_number: existing.number}) : await github.rest.issues.create(args);
    core.info(`Drift review issue: ${issue.data.html_url}`);
    return {status: 'issue_patch_not_applied', category, url: issue.data.html_url};
    } catch (_) {
      throw new Error('Drift issue publication is unavailable; retrieve the review patch from the workflow artifact.');
    }
  }
  if (!payload.edits.length) return fallback(payload.batch === 'unchecked' ? 'unchecked_sources' : 'no_status_changes_needed');
  let branchExists = false;
  let category = 'repository_policy_or_api_failure';
  try {
    if (await ref(payload.baseRef) !== base) { category = 'default_branch_changed'; throw new Error(category); }
    const pulls = await github.paginate(github.rest.pulls.list, {...common, state: 'all', head: `${owner}:${branch}`, per_page: 100});
    const existing = pulls.find(p => p.head.ref === branch && p.head.repo?.full_name === `${owner}/${repo}`);
    if (existing && existing.state !== 'open') { category = 'batch_already_closed'; throw new Error(category); }
    const previous = await ref(branch);
    branchExists = !!previous;
    const baseCommit = (await github.rest.git.getCommit({...common, commit_sha: base})).data;
    const desired = (await github.rest.git.createTree({...common, base_tree: baseCommit.tree.sha, tree: payload.edits})).data.sha;
    let head = previous;
    if (previous) {
      const prior = (await github.rest.git.getCommit({...common, commit_sha: previous})).data;
      const oldBase = prior.message.startsWith(heading) ? prior.message.slice(heading.length).trim() : '';
      if (!/^[a-f0-9]{40,64}$/.test(oldBase)) { category = 'existing_branch_has_other_edits'; throw new Error(category); }
      const original = (await github.rest.git.getCommit({...common, commit_sha: oldBase})).data;
      const expected = (await github.rest.git.createTree({...common, base_tree: original.tree.sha, tree: payload.edits})).data.sha;
      // A human edit anywhere on the existing branch changes this tree comparison.
      // Changed business definitions in the newly computed patch also require review.
      if (expected !== prior.tree.sha) { category = 'existing_branch_has_other_edits'; throw new Error(category); }
      if (oldBase === base && desired === prior.tree.sha) head = previous;
      else head = null;
    }
    if (!head) {
      const parents = previous ? [previous, base] : [base];
      head = (await github.rest.git.createCommit({...common, message: heading + base,
                tree: desired, parents})).data.sha;
      if (await ref(payload.baseRef) !== base || await ref(branch) !== previous) {
        category = 'branch_changed_during_publication'; throw new Error(category);
      }
      if (previous) await github.rest.git.updateRef({...common, ref: `heads/${branch}`, sha: head, force: false});
      else await github.rest.git.createRef({...common, ref: `refs/heads/${branch}`, sha: head});
      branchExists = true;
    }
    const args = {...common, title, body: body((regrade ? 'Eligible seed confirmations' : 'Reviewed drift status changes') +
      ' are proposed on an unmerged review branch. The default branch and lineage baseline are unchanged.')};
    const pull = existing ? await github.rest.pulls.update({...args, pull_number: existing.number}) :
      await github.rest.pulls.create({...args, head: branch, base: payload.baseRef, draft: true});
    core.info(`Drift review PR: ${pull.data.html_url}`);
    return {status: 'pr_open_not_merged', url: pull.data.html_url, branch, sha: head};
  } catch (_) {
    // Permission/policy/race failures do not turn an unapplied patch into success.
    // If issues are also disabled, this call fails and the workflow artifact remains.
    return fallback(category, branchExists);
  }
};
