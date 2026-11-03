import { execSync } from 'node:child_process';

const tests = [
  'src/tests/journeyOrchestration.test.ts',
  'src/tests/e2eFlowSimulation.test.ts',
  'src/tests/xrExperience.test.ts',
];

for (const testPath of tests) {
  const baseName = testPath.split('/').pop().replace('.ts', '');
  execSync(`npx vite build --ssr ${testPath} --outDir dist-test`, { stdio: 'inherit' });
  execSync(`node dist-test/${baseName}.js`, { stdio: 'inherit' });
}
