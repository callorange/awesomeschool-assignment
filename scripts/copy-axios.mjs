import {copyFile, mkdir} from 'node:fs/promises';

// CDN 없이 같은 버전을 배포하도록 lockfile 설치본의 ESM·source map·라이선스를 함께 복사한다.
const target = new URL('../src/static/vendor/axios/', import.meta.url);
await mkdir(target, {recursive: true});
for (const file of ['axios.min.js', 'axios.min.js.map']) {
  await copyFile(
    new URL(`../node_modules/axios/dist/esm/${file}`, import.meta.url),
    new URL(file, target),
  );
}
await copyFile(
  new URL('../node_modules/axios/LICENSE', import.meta.url),
  new URL('LICENSE', target),
);
