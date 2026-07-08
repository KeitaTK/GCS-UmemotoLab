const fs = require('fs');

const path = '/opt/homebrew/lib/node_modules/kanban/dist/cli.js';
let source = fs.readFileSync(path, 'utf8');

let changes = 0;

// Helper: apply a single-replacement patch if not already patched
function applyPatch(search, replacement, alreadyPatchedMarker, label) {
  if (source.includes(alreadyPatchedMarker)) {
    console.log('✓ Already patched: ' + label);
    return 0;
  }
  if (!source.includes(search)) {
    console.error('ERROR: Could not find code for: ' + label);
    console.error('Looking for: ' + search);
    process.exit(1);
  }
  source = source.replace(search, replacement);
  console.log('✓ Patched: ' + label);
  return 1;
}

// Patch 1: Disable host validation check
changes += applyPatch(
  'if (hostDecision.kind === "reject") {',
  'if (false) { // PATCHED: host validation disabled',
  '// PATCHED: host validation disabled',
  'host validation disabled'
);

// Patch 2: Disable CORS origin check
changes += applyPatch(
  'if (origin !== input.allowedOrigin && !isDevServer) {',
  'if (false) { // PATCHED: CORS disabled',
  '// PATCHED: CORS disabled',
  'CORS origin check disabled'
);

// Patch 3: Force-disable passcode authentication
// There are two init sites (259757, 259871) and disablePasscode() sets
// to false. Replace all assignment to true with false so patch survives
// the module initialisation.
if (source.includes('passcodeEnabled = true;') && !source.includes('// PATCHED: passcode permanently disabled')) {
  const count = (source.match(/passcodeEnabled = true;/g) || []).length;
  source = source.replace(/passcodeEnabled = true;/g, 'passcodeEnabled = false; // PATCHED: passcode permanently disabled');
  console.log(`✓ Patched: passcode authentication disabled (${count} occurrences)`);
  changes++;
} else if (source.includes('// PATCHED: passcode permanently disabled')) {
  console.log('✓ Already patched: passcode');
} else {
  console.error('ERROR: Could not find passcode code');
  process.exit(1);
}

if (changes > 0) {
  fs.writeFileSync(path, source);
  console.log(`✓ Total patches applied: ${changes}`);
} else {
  console.log('✓ All patches already applied');
}
