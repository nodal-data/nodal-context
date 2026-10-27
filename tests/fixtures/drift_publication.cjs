const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const publish = require('../../.ci/publish_drift.cjs');
const hash = x => crypto.createHash('sha1').update(JSON.stringify(x)).digest('hex');
const fail = status => { throw Object.assign(new Error('SYNTHETIC_SECRET must not reach reports'), {status}); };
function fixture() {
  const trees = {}, commits = {}, refs = {}, calls = [], issues = [], pulls = [];
  function tree(files) { const id = hash(files); trees[id] = files; return id; }
  function commit(files, message = 'human base', parents = []) {
    const t = tree(files), sha = hash({t, message, parents});
    commits[sha] = {sha, tree: {sha: t}, message, parents: parents.map(sha => ({sha}))}; return sha;
  }
  refs.main = commit({'metric.yaml': 'status: confirmed\napprover: fictional\n', '.ci/lineage-baseline.json': 'unchanged'});
  const state = {trees, commits, refs, calls, issues, pulls, commit, deny: '', race: false};
  const methods = {
    getRef: a => refs[a.ref.slice(6)] ? {object: {sha: refs[a.ref.slice(6)]}} : fail(404),
    getCommit: a => commits[a.commit_sha] || fail(404),
    createTree: a => ({sha: tree({...trees[a.base_tree], ...Object.fromEntries(a.tree.map(e => [e.path, e.content]))})}),
    createCommit: a => {
      const sha = hash(a); commits[sha] = {sha, message: a.message, tree: {sha: a.tree}, parents: a.parents.map(sha => ({sha}))};
      if (state.race) refs.main = commit({...trees[commits[refs.main].tree.sha], other: 'race'});
      return {sha};
    },
    createRef: a => { const name = a.ref.slice(11); if (refs[name]) fail(422); refs[name] = a.sha; return {}; },
    updateRef: a => { assert.equal(a.force, false); const name = a.ref.slice(6); assert(commits[a.sha].parents.some(p => p.sha === refs[name])); refs[name] = a.sha; return {}; },
  };
  const git = Object.fromEntries(Object.entries(methods).map(([name, fn]) => [name, async a => {
    calls.push({name, ...a}); if (state.deny === name) fail(403); return {data: fn(a)};
  }]));
  const gh = {
    rest: {git,
      pulls: {
        list: async () => ({data: pulls}),
        create: async a => { calls.push({name: 'pulls.create', ...a}); if (state.deny === 'pulls.create') fail(403);
          const p = {...a, number: pulls.length + 1, state: 'open', head: {ref: a.head, repo: {full_name: 'acme/context'}}, html_url: 'https://example.invalid/pr'}; pulls.push(p); return {data: p}; },
        update: async a => { calls.push({name: 'pulls.update', ...a}); const p = pulls.find(p => p.number === a.pull_number); Object.assign(p, a); return {data:p}; },
      },
      issues: {
        listForRepo: async () => ({data: issues}),
        create: async a => { if (state.deny === 'issues.create') fail(403); const i = {...a, number: issues.length + 1, html_url:'https://example.invalid/issue'}; issues.push(i); return {data:i}; },
        update: async a => { const i = issues.find(i => i.number === a.issue_number); Object.assign(i, a); return {data:i}; },
      },
    },
    paginate: async (fn, args) => (await fn(args)).data,
  };
  state.payload = {version:1, batch:'a'.repeat(20), baseSha:refs.main, baseRef:'main',
    edits:[{path:'metric.yaml', mode:'100644', type:'blob', content:'status: draft\napprover: fictional\n'}],
    report:'Affected metric and seed\n\n## Batched Stage 5 snapshot review\n\n- seed:snapshot', patch:'--- a/metric.yaml\n+++ b/metric.yaml\n-status: confirmed\n+status: draft\n'};
  state.run = payload => publish({github:gh, context:{repo:{owner:'acme',repo:'context'}, runId:42}, core:{info(){}},
    payload:payload || state.payload, artifactUrl:'https://example.invalid/artifact'});
  return state;
}
(async () => {
  let f = fixture(), initial = f.refs.main;
  let r = await f.run();
  assert.equal(r.status, 'pr_open_not_merged'); assert.equal(f.refs.main, initial);
  assert.equal(f.pulls.length, 1); assert(f.pulls[0].draft); assert(f.pulls[0].body.includes('seed:snapshot'));
  assert.equal(f.trees[f.commits[r.sha].tree.sha]['.ci/lineage-baseline.json'], 'unchanged');
  const first = r.sha;
  r = await f.run(); assert.equal(r.sha, first); assert.equal(f.pulls.length, 1);
  assert.equal(f.calls.filter(c => c.name === 'createCommit').length, 1);
  // Unrelated default-branch movement updates the same branch without discarding
  // prior proposals, and never forces a ref or overwrites unrelated files.
  const newbase = f.commit({...f.trees[f.commits[initial].tree.sha], unrelated:'new default content'}, 'human update', [initial]);
  f.refs.main = newbase; f.payload.baseSha = newbase;
  r = await f.run(); assert.equal(r.status, 'pr_open_not_merged'); assert.notEqual(r.sha, first);
  assert.equal(f.pulls.length, 1); assert.equal(f.refs.main, newbase);
  assert.equal(f.trees[f.commits[r.sha].tree.sha].unrelated, 'new default content');
  // A human edit on the proposal branch is preserved; full patch goes to issue.
  const manual = f.commit({...f.trees[f.commits[r.sha].tree.sha], human:'keep'}, 'human review', [r.sha]);
  f.refs[r.branch] = manual;
  r = await f.run(); assert.equal(r.category, 'existing_branch_has_other_edits'); assert.equal(f.refs['nodal/context-drift-'+f.payload.batch], manual);
  assert(f.issues[0].body.includes('+status: draft')); assert(f.issues[0].body.includes('not been applied to the default branch'));
  await f.run(); assert.equal(f.issues.length, 1);
  for (const deny of ['createTree', 'createCommit', 'createRef', 'pulls.create']) {
    f = fixture(); f.deny = deny; r = await f.run();
    assert.equal(r.status, 'issue_patch_not_applied'); assert.equal(f.issues.length, 1);
    assert(!f.issues[0].body.includes('SYNTHETIC_SECRET'));
    assert.equal(f.refs.main, f.payload.baseSha);
  }
  f = fixture(); f.race = true; r = await f.run();
  assert.equal(r.category, 'branch_changed_during_publication');
  assert.equal(Object.keys(f.refs).length, 1);
  f = fixture(); f.refs.main = 'b'.repeat(40); r = await f.run();
  assert.equal(r.category, 'default_branch_changed'); assert(!f.calls.some(c => c.name === 'createCommit'));
  f = fixture(); await f.run(); f.pulls[0].state = 'closed'; r = await f.run();
  assert.equal(r.category, 'batch_already_closed'); assert.equal(f.pulls.length, 1);
  f = fixture(); f.payload.edits = []; f.payload.batch = 'unchecked'; r = await f.run();
  assert.equal(r.category, 'unchecked_sources'); assert.equal(f.calls.length, 0);
  f = fixture(); f.deny = 'createRef'; f.payload.report = 'A'.repeat(70000); f.payload.patch = 'B'.repeat(70000); r = await f.run();
  assert(f.issues[0].body.length < 60000); assert(f.issues[0].body.includes('https://example.invalid/artifact'));
  f = fixture(); f.payload.edits = []; f.deny = 'issues.create'; await assert.rejects(f.run());
  f = fixture(); f.payload.purpose = 'seed-regrade'; r = await f.run();
  assert(r.branch.startsWith('nodal/seed-regrade-')); assert(f.pulls[0].title.startsWith('Restore freshly checked seeds'));
  assert(f.pulls[0].body.includes('Eligible seed confirmations'));
  console.log('drift publication API scenarios: OK');
})().catch(error => { console.error(error); process.exitCode=1; });
