import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { transformWithEsbuild } from 'vite';

assert.ok(Number(process.versions.node.split('.')[0]) >= 22);
assert.equal(renderToStaticMarkup(createElement('p', null, '环境测试')), '<p>环境测试</p>');
const result = await transformWithEsbuild('export const value: number = 42', 'environment.ts', { loader: 'ts' });
assert.ok(result.code.includes('42'));
console.log(JSON.stringify({ node: process.version, react: 'ok', vite: 'ok' }));
