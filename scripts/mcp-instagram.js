const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

// Find and parse .env file
const envPath = path.resolve(__dirname, '../.env');

let envConfig = {};
try {
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    envContent.split('\n').forEach(line => {
      const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)?\s*$/);
      if (match) {
        let key = match[1];
        let val = match[2] || '';
        // Remove quotes if present
        if (val.length > 0 && val.charAt(0) === '"' && val.charAt(val.length - 1) === '"') {
          val = val.substring(1, val.length - 1);
        } else if (val.length > 0 && val.charAt(0) === "'" && val.charAt(val.length - 1) === "'") {
          val = val.substring(1, val.length - 1);
        }
        envConfig[key] = val.trim();
      }
    });
  }
} catch (err) {
  console.error('[mcp-wrapper] Error reading .env file:', err);
}

const apiHost = envConfig['RAPIDAPI_HOST'] || 'instagram-scraper-stable-api.p.rapidapi.com';
const apiKey = envConfig['RAPIDAPI_KEY'];

if (!apiKey) {
  console.error('[mcp-wrapper] Error: RAPIDAPI_KEY is not defined in .env');
  process.exit(1);
} else {
  console.error(`[mcp-wrapper] Loaded RAPIDAPI_KEY (len: ${apiKey.length}), RAPIDAPI_HOST: ${apiHost}`);
}

// Resolve local mcp-remote executable path to avoid slow npx registry/cache checks
const mcpRemoteBin = path.resolve(
  __dirname,
  '../node_modules/.bin/mcp-remote' + (process.platform === 'win32' ? '.cmd' : '')
);

const useLocal = fs.existsSync(mcpRemoteBin);
const command = useLocal
  ? (process.platform === 'win32' ? `"${mcpRemoteBin}"` : mcpRemoteBin)
  : (process.platform === 'win32' ? 'npx.cmd' : 'npx');
const args = useLocal
  ? [
      'https://mcp.rapidapi.com',
      '--header', `x-api-host: ${apiHost}`,
      '--header', `x-api-key: ${apiKey}`
    ]
  : [
      'mcp-remote',
      'https://mcp.rapidapi.com',
      '--header', `x-api-host: ${apiHost}`,
      '--header', `x-api-key: ${apiKey}`
    ];

const child = spawn(command, args, {
  stdio: ['pipe', 'pipe', 'inherit'],
  shell: true
});

// Pipe stdin to the child and stdout back to parent
process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);

child.on('close', (code) => {
  process.exit(code);
});
