import fs from 'node:fs';
const base = (process.env.VOICELAB_API_BASE || '').replace(/\/$/, '');
if (!base) {
  console.warn('VOICELAB_API_BASE is not set. The frontend will try same-origin /api routes.');
}
fs.writeFileSync('apps/web/config.js', `window.VOICELAB_API_BASE = ${JSON.stringify(base)};\n`);
console.log(`VoiceLab frontend configured for API: ${base || '(same origin)'}`);
