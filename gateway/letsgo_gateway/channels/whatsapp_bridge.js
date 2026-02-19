#!/usr/bin/env node
/**
 * WhatsApp Web bridge for the letsgo gateway.
 *
 * Wraps whatsapp-web.js and communicates with the Python adapter
 * via JSON lines on stdin/stdout.
 *
 * Stdout (bridge → Python):
 *   { "type": "qr",         "data": "<qr_string>" }
 *   { "type": "ready",      "data": { "phone": "..." } }
 *   { "type": "message",    "data": { "id", "from", "sender", "text", "files", ... } }
 *   { "type": "disconnect", "data": { "reason": "..." } }
 *   { "type": "error",      "data": { "message": "..." } }
 *
 * Stdin (Python → bridge):
 *   { "type": "send",    "data": { "to": "...", "text": "...", "files": [...] } }
 *   { "type": "typing",  "data": { "to": "..." } }
 *   { "type": "shutdown" }
 */

const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const readline = require("readline");

// --- config from env ---
const SESSION_DIR = process.env.WHATSAPP_SESSION_DIR || path.join(process.env.HOME, ".letsgo", "whatsapp-session");
const FILES_DIR = process.env.WHATSAPP_FILES_DIR || path.join(process.env.HOME, ".letsgo", "whatsapp-files");
const QR_FILE = process.env.WHATSAPP_QR_FILE || path.join(process.env.HOME, ".letsgo", "whatsapp_qr.txt");

// ensure dirs exist
fs.mkdirSync(SESSION_DIR, { recursive: true });
fs.mkdirSync(FILES_DIR, { recursive: true });
fs.mkdirSync(path.dirname(QR_FILE), { recursive: true });

// --- helpers ---

function emit(type, data) {
  process.stdout.write(JSON.stringify({ type, data }) + "\n");
}

const MIME_EXT = {
  "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
  "image/webp": ".webp", "audio/ogg": ".ogg", "audio/mpeg": ".mp3",
  "audio/mp4": ".m4a", "video/mp4": ".mp4", "application/pdf": ".pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
  "text/plain": ".txt",
};

const MEDIA_TYPES = new Set(["image", "audio", "ptt", "video", "document", "sticker"]);

async function downloadMedia(msg) {
  if (!msg.hasMedia) return null;
  try {
    const media = await msg.downloadMedia();
    if (!media || !media.data) return null;
    const ext = MIME_EXT[media.mimetype] || ".bin";
    const filename = `wa_${msg.id.id}_${Date.now()}${ext}`;
    const filepath = path.join(FILES_DIR, filename);
    fs.writeFileSync(filepath, Buffer.from(media.data, "base64"));
    return { path: filepath, mimetype: media.mimetype, filename: media.filename || filename };
  } catch (e) {
    emit("error", { message: `Media download failed: ${e.message}` });
    return null;
  }
}

// --- client setup ---

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_DIR }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--no-first-run",
      "--disable-gpu",
    ],
  },
});

client.on("qr", (qr) => {
  qrcode.generate(qr, { small: true }, (qrArt) => {
    process.stderr.write("\n" + qrArt + "\n");
    process.stderr.write("Scan QR code with WhatsApp to connect\n\n");
  });
  try { fs.writeFileSync(QR_FILE, qr); } catch {}
  emit("qr", qr);
});

client.on("ready", async () => {
  const info = client.info;
  const phone = info && info.wid ? info.wid.user : "unknown";
  process.stderr.write(`WhatsApp connected (${phone})\n`);
  emit("ready", { phone });
});

client.on("disconnected", (reason) => {
  process.stderr.write(`WhatsApp disconnected: ${reason}\n`);
  emit("disconnect", { reason: String(reason) });
});

client.on("auth_failure", (msg) => {
  emit("error", { message: `Auth failure: ${msg}` });
});

// --- inbound messages ---

client.on("message_create", async (msg) => {
  // skip our own messages and group messages
  if (msg.fromMe) return;
  const chat = await msg.getChat();
  if (chat.isGroup) return;

  const contact = await msg.getContact();
  const sender = contact.pushname || contact.name || contact.number || msg.from;

  // download media if present
  const files = [];
  if (msg.hasMedia && MEDIA_TYPES.has(msg.type)) {
    const file = await downloadMedia(msg);
    if (file) files.push(file);
  }

  // build text body
  let text = msg.body || "";
  for (const f of files) {
    text += `\n[file: ${f.path}]`;
  }

  emit("message", {
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    from: msg.from,
    sender,
    text,
    files: files.map((f) => f.path),
    timestamp: msg.timestamp,
    messageType: msg.type,
  });

  // show typing while gateway processes
  try { await chat.sendStateTyping(); } catch {}
});

// --- stdin commands (Python → bridge) ---

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on("line", async (line) => {
  let cmd;
  try {
    cmd = JSON.parse(line);
  } catch {
    return;
  }

  if (cmd.type === "send") {
    const { to, text, files } = cmd.data || {};
    try {
      const chat = await client.getChatById(to);

      // send files first
      if (files && files.length) {
        for (const filepath of files) {
          try {
            const media = MessageMedia.fromFilePath(filepath);
            await chat.sendMessage(media);
          } catch (e) {
            emit("error", { message: `File send failed: ${e.message}` });
          }
        }
      }

      // send text
      if (text) {
        await chat.sendMessage(text);
      }
    } catch (e) {
      emit("error", { message: `Send failed to ${to}: ${e.message}` });
    }
  } else if (cmd.type === "typing") {
    try {
      const chat = await client.getChatById(cmd.data.to);
      await chat.sendStateTyping();
    } catch {}
  } else if (cmd.type === "shutdown") {
    process.stderr.write("Shutting down WhatsApp bridge\n");
    try { await client.destroy(); } catch {}
    process.exit(0);
  }
});

rl.on("close", async () => {
  try { await client.destroy(); } catch {}
  process.exit(0);
});

// --- start ---

process.stderr.write("Starting WhatsApp bridge...\n");
client.initialize().catch((e) => {
  emit("error", { message: `Failed to initialize: ${e.message}` });
  process.exit(1);
});
