const { app, safeStorage } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const CONFIG_VERSION = 1;

function configPath() {
  return path.join(app.getPath("userData"), "runtime-config.json");
}

function readStoredConfig() {
  try {
    const value = JSON.parse(fs.readFileSync(configPath(), "utf8"));
    return value?.version === CONFIG_VERSION ? value : null;
  } catch {
    return null;
  }
}

function decrypt(value) {
  return safeStorage.decryptString(Buffer.from(value, "base64"));
}

function encrypt(value) {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error("当前系统无法使用安全凭据存储，请检查 Windows 登录账户设置");
  }
  return safeStorage.encryptString(value).toString("base64");
}

function validateIdentifier(value, label) {
  const text = String(value || "").trim();
  if (!/^[A-Za-z0-9_$-]{1,64}$/.test(text)) {
    throw new Error(`${label}只能包含字母、数字、下划线、$ 或短横线`);
  }
  return text;
}

function normalizeInput(input) {
  const host = String(input.host || "").trim();
  if (!host || host.length > 255 || /[\s/@?#]/.test(host)) {
    throw new Error("MySQL 主机地址格式不正确");
  }
  const port = Number(input.port || 3306);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("MySQL 端口必须是 1 到 65535 之间的整数");
  }
  const username = validateIdentifier(input.username, "数据库用户名");
  const database = validateIdentifier(input.database, "数据库名");
  const password = String(input.password || "");
  if (!password || password.length > 512 || /[\r\n]/.test(password)) {
    throw new Error("数据库密码不能为空且不能包含换行符");
  }
  return { host, port, username, database, password };
}

function saveRuntimeConfig(input) {
  const value = normalizeInput(input);
  const previous = readStoredConfig();
  const stored = {
    version: CONFIG_VERSION,
    host: value.host,
    port: value.port,
    username: value.username,
    database: value.database,
    password: encrypt(value.password),
    secretKey: previous?.secretKey || encrypt(crypto.randomBytes(48).toString("base64url")),
    updatedAt: new Date().toISOString(),
  };
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  fs.writeFileSync(configPath(), JSON.stringify(stored, null, 2), {
    encoding: "utf8",
    mode: 0o600,
  });
  return publicRuntimeConfig(stored);
}

function publicRuntimeConfig(stored = readStoredConfig()) {
  if (!stored) return { configured: false };
  return {
    configured: true,
    host: stored.host,
    port: stored.port,
    username: stored.username,
    database: stored.database,
    updated_at: stored.updatedAt,
  };
}

function backendEnvironment() {
  const stored = readStoredConfig();
  if (!stored) return null;
  const password = decrypt(stored.password);
  const databaseUrl =
    `mysql+pymysql://${encodeURIComponent(stored.username)}:` +
    `${encodeURIComponent(password)}@${stored.host}:${stored.port}/` +
    `${stored.database}?charset=utf8mb4`;
  return {
    DATABASE_URL: databaseUrl,
    SECRET_KEY: decrypt(stored.secretKey),
  };
}

module.exports = {
  backendEnvironment,
  publicRuntimeConfig,
  readStoredConfig,
  saveRuntimeConfig,
};
