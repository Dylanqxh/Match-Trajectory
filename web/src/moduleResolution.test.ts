import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const sourceRoot = path.join(root, "web", "src");
const extensions = [".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json"];
const importPattern = /(?:from|import)\s*(?:\(\s*)?["'](\.[^"']+)["']/g;

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap(name => {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(tsx?|jsx?|mjs|cjs)$/.test(name) ? [full] : [];
  });
}

function resolveSpecifier(fromFile: string, specifier: string, caseSensitive: boolean): string | null {
  const base = path.resolve(path.dirname(fromFile), specifier.split("?")[0]);
  const candidates = path.extname(base) ? [base] : [base, ...extensions.map(extension => base + extension)];
  const directory = path.dirname(candidates[0]);
  let names: string[] = [];
  try { names = readdirSync(directory); } catch { return null; }
  for (const candidate of candidates) {
    const wanted = path.basename(candidate);
    const found = names.find(name => caseSensitive ? name === wanted : name.toLowerCase() === wanted.toLowerCase());
    if (!found) continue;
    const full = path.join(directory, found);
    if (statSync(full).isFile()) return full;
  }
  return null;
}

describe("extensionless imports on a case-insensitive filesystem", () => {
  it("resolves the same file Vite would choose on Windows and Linux", () => {
    const collisions: string[] = [];
    for (const file of sourceFiles(sourceRoot)) {
      const text = readFileSync(file, "utf8");
      for (const match of text.matchAll(importPattern)) {
        const specifier = match[1];
        const linux = resolveSpecifier(file, specifier, true);
        const windows = resolveSpecifier(file, specifier, false);
        if (linux !== windows) {
          collisions.push(`${path.relative(root, file)} imports ${specifier}: Linux ${linux ? path.relative(root, linux) : "missing"}, Windows ${windows ? path.relative(root, windows) : "missing"}`);
        }
      }
    }
    expect(collisions).toEqual([]);
  });
});
