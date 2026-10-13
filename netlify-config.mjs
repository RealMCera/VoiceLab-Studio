import fs from 'node:fs';
import path from 'node:path';

const base = (process.env.VOICELAB_API_BASE || '').replace(/\/$/, '');
if (!base) {
  console.warn('VOICELAB_API_BASE is not set. The frontend will try same-origin /api routes.');
}

const out = 'netlify-dist';
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
for (const file of ['index.html', 'app.js', 'styles.css']) {
  fs.copyFileSync(file, path.join(out, file));
}
fs.writeFileSync(path.join(out, 'config.js'), `window.VOICELAB_API_BASE = ${JSON.stringify(base)};\n`);
console.log(`VoiceLab frontend configured for API: ${base || '(same origin)'}`);
