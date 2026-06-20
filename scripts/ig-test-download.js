const fs = require('fs');
const path = require('path');
const https = require('https');

const jsonPath = 'C:\\Users\\heebo\\.gemini\\antigravity\\brain\\0e96c98e-9efd-49cf-9a89-511ee4a9cc17\\.system_generated\\steps\\3903\\output.txt';
const destDir = 'c:\\Users\\heebo\\Documents\\Vibecoding Projects\\Areopagus\\brain\\ig';

// Create destination directory if not exists
if (!fs.existsSync(destDir)) {
  fs.mkdirSync(destDir, { recursive: true });
}

// Read JSON
const rawData = fs.readFileSync(jsonPath, 'utf8');
const data = JSON.parse(rawData);

const edges = data.posts.edges;
console.log(`Found ${edges.length} posts.`);

// Sort by comment count or like count if available, or just get the first few
// The API has:
// edge_media_to_comment: { count: X }
// edge_liked_by: { count: X }
// Let's sort by comment count or grab the first 5 with valid display_url
const items = edges
  .map(edge => {
    const node = edge.node;
    const likes = node.edge_liked_by ? node.edge_liked_by.count : 0;
    const comments = node.edge_media_to_comment ? node.edge_media_to_comment.count : 0;
    const caption = node.edge_media_to_caption && node.edge_media_to_caption.edges.length > 0 
      ? node.edge_media_to_caption.edges[0].node.text 
      : '';
    return {
      id: node.id,
      shortcode: node.shortcode,
      url: node.display_url,
      likes,
      comments,
      caption,
      isVideo: node.is_video
    };
  })
  .filter(item => item.url && !item.isVideo) // only images
  .slice(0, 5); // take top 5

console.log(`Downloading ${items.length} images...`);

function downloadFile(url, destPath) {
  return new Promise((resolve, reject) => {
    https.get(url, (response) => {
      if (response.statusCode !== 200) {
        reject(new Error(`Failed to get '${url}' (${response.statusCode})`));
        return;
      }
      const fileStream = fs.createWriteStream(destPath);
      response.pipe(fileStream);
      fileStream.on('finish', () => {
        fileStream.close();
        resolve();
      });
      fileStream.on('error', (err) => {
        fs.unlink(destPath, () => {});
        reject(err);
      });
    }).on('error', (err) => {
      reject(err);
    });
  });
}

async function run() {
  const manifest = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const filename = `${item.shortcode}.jpg`;
    const destPath = path.join(destDir, filename);
    console.log(`[${i+1}/${items.length}] Downloading ${filename}...`);
    try {
      await downloadFile(item.url, destPath);
      manifest.push({
        filename,
        likes: item.likes,
        comments: item.comments,
        caption: item.caption.substring(0, 100) + (item.caption.length > 100 ? '...' : '')
      });
    } catch (err) {
      console.error(`Failed to download ${item.shortcode}: ${err.message}`);
    }
  }

  // Create a markdown index file in the folder for easy viewing
  const mdContent = `# Scraped Instagram Design Inspiration

This folder contains a test batch of high-engagement images scraped from Instagram under the tag **#industrialdesign**.

${manifest.map((m, idx) => `
### ${idx + 1}. [${m.filename}](file:///${path.join(destDir, m.filename).replace(/\\/g, '/')})
* **Engagement:** ${m.likes} Likes | ${m.comments} Comments
* **Caption:** ${m.caption}
![${m.filename}](file:///${path.join(destDir, m.filename).replace(/\\/g, '/')})
`).join('\n')}
`;
  
  fs.writeFileSync(path.join(destDir, 'README.md'), mdContent, 'utf8');
  console.log(`Finished. Saved README.md to ${destDir}`);
}

run().catch(console.error);
