import { execSync } from 'node:child_process';

const tests = [
  'src/tests/journeyOrchestration.test.ts',
  'src/tests/e2eFlowSimulation.test.ts',
  'src/tests/xrExperience.test.ts',
  'src/tests/journeyMap.test.ts',
  'src/tests/optimizer.test.ts',
  'src/tests/apiContracts.test.ts',
  'src/tests/trustAwareJourney.test.ts',
  'src/tests/multimodalRoutingIntelligence.test.ts',
  'src/tests/gpsStartingLocation.test.ts',
  'src/tests/navigationGuidance.test.ts',
  'src/tests/disruptionIntelligence.test.ts',
  'src/tests/dynamicJourneyMapSync.test.ts',
  'src/tests/fallbackOriginSync.test.ts',
  'src/tests/gpsCollisionDetector.test.ts',
  'src/tests/nullIslandAvoidance.test.ts',
];

for (const testPath of tests) {
  const baseName = testPath.split('/').pop().replace('.ts', '');
  execSync(`node --max-old-space-size=4096 ./node_modules/vite/bin/vite.js build --ssr ${testPath} --outDir dist-test`, {
    stdio: 'inherit',
    env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=4096' },
  });
  execSync(`node dist-test/${baseName}.js`, { stdio: 'inherit' });
}
