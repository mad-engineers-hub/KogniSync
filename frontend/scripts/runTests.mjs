import { execSync } from 'node:child_process';

try {
  execSync('npx vite build --ssr src/tests/journeyOrchestration.test.ts --outDir dist-test', { stdio: 'inherit' });
  execSync('node dist-test/journeyOrchestration.test.js', { stdio: 'inherit' });
} catch (err) {
  process.exit(1);
}

