// Make a local test edition of the pinned HWP. All replacements are unique and
// equal-width so character counts, table geometry and record offsets stay valid.
const fs = require("node:fs");
const zlib = require("node:zlib");
const { createRequire } = require("node:module");

const cfb = createRequire(process.argv[2])("cfb");
const doc = cfb.read(fs.readFileSync(0), { type: "buffer" });
const section = cfb.find(doc, "/BodyText/Section0");
if (!section) throw Error("Missing BodyText/Section0");
const records = zlib.inflateRawSync(section.content);
const changes = JSON.parse(process.argv[3]).map(([a, b]) => {
  const from = Buffer.from(a, "utf16le"), to = Buffer.from(b, "utf16le");
  if (!from.length || from.length !== to.length) throw Error("Expected equal-width replacements");
  return {from, to, hits:0};
});
for (let offset = 0; offset < records.length;) {
  const header = records.readUInt32LE(offset);
  offset += 4;
  let size = header >>> 20;
  if (size === 4095) {
    size = records.readUInt32LE(offset);
    offset += 4;
  }
  if (offset + size > records.length) throw Error("Invalid HWP record");
  if ((header & 1023) === 67) {
    const para = records.subarray(offset, offset + size);
    for (const change of changes) {
      let pos = para.indexOf(change.from);
      while (pos >= 0) {
        change.to.copy(para, pos);
        change.hits++;
        pos = para.indexOf(change.from, pos + change.to.length);
      }
    }
  }
  offset += size;
}
if (changes.some(change => change.hits !== 1)) throw Error("Expected one original paragraph span per edit");
section.content = zlib.deflateRawSync(records);
section.size = section.content.length;
process.stdout.write(cfb.write(doc, {type:"buffer"}));
