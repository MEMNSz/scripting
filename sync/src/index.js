// Scripting · servidor propio (cada anfitrión lo sube a SU cuenta de Cloudflare).
// Hub (un solo Durable Object): cuentas, sesiones, invitación y lista de salas.
// Room (uno por guion): guarda el guion y reparte los cambios en vivo.
//
// API (JSON, token en "Authorization: Bearer <token>"):
//   GET  /api/info                         -> {ok, setup:bool(ya tiene admin), version}
//   POST /api/setup {key,name,password,color}  primer admin (key = SETUP_KEY del deploy)
//   POST /api/login {name,password}        POST /api/join {invite,name,password,color}
//   GET  /api/me   POST /api/me {color?,password?}   POST /api/logout
//   GET  /api/rooms   POST /api/rooms {name}   DELETE /api/rooms/<id>
//   GET  /api/admin   POST /api/admin {op:"kick"|"role"|"invite"|"invites", ...}
// WebSocket: /sala/<id>?token=<token>
//   cliente -> {t:"hello"} {t:"up",u} {t:"snap",u,upto} {t:"aw",s} {t:"ping"}     (u = cambio Yjs en base64)
//   servidor -> {t:"init",me,users,log:[{seq,u}]} {t:"up",u,seq,by} {t:"ack",seq} {t:"aw",by,s} {t:"users",users} {t:"kicked"}
import { DurableObject } from "cloudflare:workers";

const VERSION = 6;
const MAX_MSG = 4 * 1024 * 1024, CHUNK = 100 * 1024;
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS" };
const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json", ...CORS } });
const hub = env => env.HUB.get(env.HUB.idFromName("hub"));
const rnd = n => [...crypto.getRandomValues(new Uint8Array(n))].map(b => b.toString(16).padStart(2, "0")).join("");
const sha = async s => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)))].map(b => b.toString(16).padStart(2, "0")).join("");
async function pbkdf2(pw, salt) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: new TextEncoder().encode(salt), iterations: 100000 }, k, 256);
  return [...new Uint8Array(bits)].map(b => b.toString(16).padStart(2, "0")).join("");
}
const okName = s => typeof s === "string" && /^[\p{L}\p{N} ._-]{2,30}$/u.test(s.trim());
const okColor = c => typeof c === "string" && /^#[0-9a-f]{6}$/i.test(c);
const okPw = p => typeof p === "string" && p.length >= 6 && p.length <= 200;
const pub = u => ({ id: u.id, name: u.name, color: u.color, role: u.role });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (url.pathname.startsWith("/api/")) {
      const body = req.method === "POST" ? await req.json().catch(() => ({})) : {};
      const token = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
      const r = await hub(env).api(req.method, url.pathname.slice(5), body, token, env.SETUP_KEY || "");
      if (r.kick) await Promise.all(r.rooms.map(id => env.ROOMS.get(env.ROOMS.idFromName(id)).kick(r.kick)));   // lo saca de las salas abiertas
      return json(r.body, r.status || 200);
    }
    const im = url.pathname.match(/^\/img\/([0-9a-f]{40}\.(jpg|png|webp|gif))$/);
    if (im) {   // imágenes compartidas de la sala (el nombre es la huella SHA-1 del archivo)
      const token = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
      if (req.method === "PUT") {
        const buf = await req.arrayBuffer();
        if (buf.byteLength > 15e6) return json({ error: "imagen muy grande (máx. 15 MB)" }, 413);
        const r = await hub(env).imgPut(token, im[1], buf);
        return json(r.body, r.status || 200);
      }
      const r = await hub(env).imgGet(token, im[1]);
      if (!r) return json({ error: "no existe o sin permiso" }, 404);
      return new Response(r, { headers: { "Content-Type": { jpg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif" }[im[2]], "Cache-Control": "private, max-age=31536000, immutable", ...CORS } });
    }
    const m = url.pathname.match(/^\/sala\/([a-f0-9]{16})$/);
    if (m) {
      if (req.headers.get("Upgrade") !== "websocket") return json({ error: "se espera WebSocket" }, 426);
      const who = await hub(env).check(url.searchParams.get("token") || "", m[1]);
      if (!who) return json({ error: "sin permiso" }, 403);
      const h = new Headers(req.headers); h.set("X-User", JSON.stringify(who));
      return env.ROOMS.get(env.ROOMS.idFromName(m[1])).fetch(new Request(req.url, { headers: h }));
    }
    return new Response("Scripting · servidor de salas", { headers: CORS });
  },
};

export class Hub extends DurableObject {
  get s() { return this.ctx.storage; }
  async user(token) {
    if (!token) return null;
    const id = await this.s.get("sess:" + await sha(token));
    const u = id && await this.s.get("user:" + id);
    return u && !u.off ? u : null;
  }
  async session(u) {
    const t = rnd(32);
    await this.s.put("sess:" + await sha(t), u.id);
    return { token: t, user: pub(u) };
  }
  async create(name, password, color, role) {
    name = name.trim();
    if (await this.s.get("uname:" + name.toLowerCase())) return null;
    const salt = rnd(16), u = { id: rnd(6), name, color, role, salt, hash: await pbkdf2(password, salt), at: Date.now() };
    await this.s.put({ ["user:" + u.id]: u, ["uname:" + name.toLowerCase()]: u.id });
    return u;
  }
  async users() { return [...(await this.s.list({ prefix: "user:" })).values()]; }
  async rooms() { return (await this.s.get("rooms")) || []; }

  // imágenes: se guardan en pedazos de 512 KB
  async imgPut(token, name, buf) {
    if (!(await this.user(token))) return { status: 401, body: { error: "sin permiso" } };
    if (await this.s.get("img:" + name)) return { body: { ok: true, had: true } };
    const h = [...new Uint8Array(await crypto.subtle.digest("SHA-1", buf))].map(b => b.toString(16).padStart(2, "0")).join("");
    if (h !== name.slice(0, 40)) return { status: 400, body: { error: "la imagen no coincide con su nombre" } };
    const C = 512 * 1024, n = Math.max(1, Math.ceil(buf.byteLength / C)), o = {};
    for (let i = 0; i < n; i++) o["img:" + name + ":" + i] = buf.slice(i * C, (i + 1) * C);
    o["img:" + name] = n;
    await this.s.put(o);
    return { body: { ok: true } };
  }
  async imgGet(token, name) {
    if (!(await this.user(token))) return null;
    const n = await this.s.get("img:" + name);
    if (!n) return null;
    const keys = Array.from({ length: n }, (_, i) => "img:" + name + ":" + i), parts = await this.s.get(keys);
    const out = new Uint8Array(keys.reduce((a, k) => a + (parts.get(k)?.byteLength || 0), 0));
    let off = 0; for (const k of keys) { const p = new Uint8Array(parts.get(k)); out.set(p, off); off += p.byteLength; }
    return out.buffer;
  }
  async imgHave(names) {
    const out = [];
    for (const n of names.slice(0, 500)) if (typeof n === "string" && await this.s.get("img:" + n)) out.push(n);
    return out;
  }
  // lo llama el Worker antes de abrir una sala
  async check(token, room) {
    const u = await this.user(token);
    if (!u || !(await this.rooms()).some(r => r.id === room)) return null;
    return pub(u);
  }

  async api(method, path, b, token, setupKey) {
    const E = (error, status = 400) => ({ status, body: { error } });
    const route = method + " " + path.replace(/\/[a-f0-9]{16}$/, "/:id");
    if (route === "GET info") return { body: { ok: true, setup: !!(await this.s.get("admin")), version: VERSION } };
    if (route === "POST setup") {
      if (await this.s.get("admin")) return E("este servidor ya tiene anfitrión", 409);
      if (!setupKey || b.key !== setupKey) return E("clave de instalación incorrecta", 403);
      if (!okName(b.name) || !okPw(b.password) || !okColor(b.color)) return E("datos inválidos");
      const u = await this.create(b.name, b.password, b.color, "admin");
      await this.s.put({ admin: u.id, invite: rnd(8), invites: true });
      return { body: await this.session(u) };
    }
    if (route === "POST login") {
      const id = okName(b.name) && await this.s.get("uname:" + b.name.trim().toLowerCase());
      const u = id && await this.s.get("user:" + id);
      if (!u || u.off || await pbkdf2(String(b.password || ""), u.salt) !== u.hash) { await new Promise(r => setTimeout(r, 600)); return E("usuario o contraseña incorrectos", 401); }
      return { body: await this.session(u) };
    }
    if (route === "POST join") {
      if (!(await this.s.get("invites")) || !b.invite || b.invite !== await this.s.get("invite")) return E("la invitación no vale (pedile una nueva al anfitrión)", 403);
      if (!okName(b.name) || !okPw(b.password) || !okColor(b.color)) return E("nombre (2-30), contraseña (6+) o color inválidos");
      const u = await this.create(b.name, b.password, b.color, "member");
      if (!u) return E("ese nombre ya está usado", 409);
      return { body: await this.session(u) };
    }

    const me = await this.user(token);
    if (!me) return E("sesión vencida, volvé a entrar", 401);
    const admin = me.role === "admin";
    switch (route) {
      case "GET me": return { body: { user: pub(me) } };
      case "POST imghave": return { body: { have: await this.imgHave(Array.isArray(b.names) ? b.names : []) } };
      case "POST me":
        if (b.color !== undefined) { if (!okColor(b.color)) return E("color inválido"); me.color = b.color; }
        if (b.password !== undefined) { if (!okPw(b.password)) return E("la contraseña necesita 6 caracteres o más"); me.salt = rnd(16); me.hash = await pbkdf2(b.password, me.salt); }
        await this.s.put("user:" + me.id, me);
        return { body: { user: pub(me) } };
      case "POST logout": await this.s.delete("sess:" + await sha(token)); return { body: { ok: true } };
      case "GET rooms": return { body: { rooms: await this.rooms() } };
      case "POST rooms": {
        const name = String(b.name || "").trim().slice(0, 80) || "Guion sin título";
        const rooms = await this.rooms(), r = { id: rnd(8), name, owner: me.id, at: Date.now() };
        rooms.push(r); await this.s.put("rooms", rooms);
        return { body: { room: r } };
      }
      case "DELETE rooms/:id": {
        const id = path.slice(-16), rooms = await this.rooms(), r = rooms.find(x => x.id === id);
        if (!r) return E("no existe", 404);
        if (!admin && r.owner !== me.id) return E("solo el dueño o el anfitrión", 403);
        await this.s.put("rooms", rooms.filter(x => x.id !== id));
        return { body: { ok: true } };
      }
      case "GET admin":
        if (!admin) return E("solo el anfitrión", 403);
        return { body: { users: (await this.users()).map(u => ({ ...pub(u), off: !!u.off, at: u.at })), invite: await this.s.get("invite"), invites: !!(await this.s.get("invites")), rooms: await this.rooms() } };
      case "POST admin": {
        if (!admin) return E("solo el anfitrión", 403);
        if (b.op === "invite") { const inv = rnd(8); await this.s.put("invite", inv); return { body: { invite: inv } }; }
        if (b.op === "invites") { await this.s.put("invites", !!b.on); return { body: { invites: !!b.on } }; }
        const u = await this.s.get("user:" + b.id);
        if (!u || u.id === me.id) return E("no se puede con ese usuario");
        if (b.op === "kick") u.off = !b.back;          // desactivar (o reactivar con back:true)
        else if (b.op === "role") u.role = b.role === "admin" ? "admin" : "member";
        else if (b.op === "delete") { await this.s.delete(["user:" + u.id, "uname:" + u.name.toLowerCase()]); return { kick: u.id, rooms: (await this.rooms()).map(r => r.id), body: { ok: true } }; }
        else return E("operación desconocida");
        await this.s.put("user:" + u.id, u);
        const cut = u.off ? { kick: u.id, rooms: (await this.rooms()).map(r => r.id) } : {};
        return { ...cut, body: { user: { ...pub(u), off: !!u.off } } };
      }
    }
    return E("no existe", 404);
  }
}

export class Room extends DurableObject {
  // Guarda la historia de cambios Yjs (en base64) y la reparte. Los clientes la compactan de vez en cuando.
  async fetch(req) {
    const who = JSON.parse(req.headers.get("X-User"));
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server);   // con hibernación: no consume mientras nadie escribe
    server.serializeAttachment({ ...who, sid: rnd(4), aw: null });
    return new Response(null, { status: 101, webSocket: client });
  }
  users(skip) { return this.ctx.getWebSockets().filter(w => w !== skip).map(w => w.deserializeAttachment()).filter(Boolean); }
  send(ws, msg) { try { ws.send(typeof msg === "string" ? msg : JSON.stringify(msg)); } catch {} }
  others(from, msg) { const s = JSON.stringify(msg); for (const ws of this.ctx.getWebSockets()) if (ws !== from) this.send(ws, s); }
  key(seq) { return typeof seq === "string" ? "x:" + seq : "u:" + String(seq).padStart(10, "0"); }
  async put(seq, data) {
    const n = Math.max(1, Math.ceil(data.length / CHUNK)), o = { [this.key(seq)]: n };
    for (let i = 0; i < n; i++) o[this.key(seq) + ":" + i] = data.slice(i * CHUNK, (i + 1) * CHUNK);
    await this.ctx.storage.put(o);
  }
  async log() {
    const all = await this.ctx.storage.list({ prefix: "u:" }), out = [];
    for (const [k, v] of all) if (k.length === 12) out.push({ seq: +k.slice(2), u: Array.from({ length: v }, (_, i) => all.get(k + ":" + i) || "").join("") });
    return out;
  }
  async webSocketMessage(ws, raw) {
    if (typeof raw !== "string" || raw.length > MAX_MSG) return;
    let m; try { m = JSON.parse(raw); } catch { return; }
    const me = ws.deserializeAttachment();
    switch (m.t) {
      case "hello":
        await this.act(me, { key: "join:" + me.id, kind: "join", verb: "entró a la sala", label: "" }, 30 * 60e3);
        this.send(ws, { t: "init", me: me.sid, users: this.users(), log: await this.log(), acts: (await this.ctx.storage.get("acts")) || [] });
        this.others(ws, { t: "users", users: this.users() });
        break;
      case "up": {   // un cambio: se numera, se guarda y se reparte
        if (typeof m.u !== "string") break;
        const seq = ((await this.ctx.storage.get("seq")) || 0) + 1;
        await this.ctx.storage.put("seq", seq); await this.put(seq, m.u);
        this.send(ws, { t: "ack", seq });
        this.others(ws, { t: "up", u: m.u, seq, by: me.sid });
        break;
      }
      case "snap": {   // compactar: un solo cambio que reemplaza todos hasta "upto"
        const upto = +m.upto;
        if (typeof m.u !== "string" || !(upto > 0)) break;
        const del = [...(await this.ctx.storage.list({ prefix: "u:", end: this.key(upto + 1) })).keys()];
        for (let i = 0; i < del.length; i += 128) await this.ctx.storage.delete(del.slice(i, i + 128));
        await this.put(upto, m.u);
        break;
      }
      case "ver": {   // guardar una versión con nombre, autor y hora
        if (typeof m.u !== "string") break;
        const v = { id: rnd(6), at: Date.now(), name: String(m.name || "").trim().slice(0, 80) || "Versión sin nombre", by: { id: me.id, name: me.name, color: me.color } };
        await this.put("v" + v.id, m.u);
        const list = (await this.ctx.storage.get("vers")) || []; list.unshift(v); await this.ctx.storage.put("vers", list.slice(0, 200));
        this.others(null, { t: "vers", list: list.slice(0, 200) });
        await this.act(me, { key: "ver:" + v.id, kind: "ver", verb: "guardó la versión", label: v.name }, 0);
        break;
      }
      case "act":   // actividad: qué hizo cada uno (se agrupa por tema durante 2 minutos)
        if (m.e && typeof m.e === "object") await this.act(me, m.e, 120e3);
        break;
      case "vers": this.send(ws, { t: "vers", list: (await this.ctx.storage.get("vers")) || [] }); break;
      case "verget": {
        const k = this.key("v" + String(m.id).replace(/[^a-f0-9]/g, "")), n = await this.ctx.storage.get(k);
        if (!n) { this.send(ws, { t: "verdata", id: m.id, u: null }); break; }
        const parts = await this.ctx.storage.get(Array.from({ length: n }, (_, i) => k + ":" + i));
        this.send(ws, { t: "verdata", id: m.id, u: Array.from({ length: n }, (_, i) => parts.get(k + ":" + i) || "").join("") });
        break;
      }
      case "verdel": {
        const list = (await this.ctx.storage.get("vers")) || [], v = list.find(x => x.id === m.id);
        if (!v || (v.by.id !== me.id && me.role !== "admin")) break;
        const k = this.key("v" + v.id), n = (await this.ctx.storage.get(k)) || 0;
        await this.ctx.storage.delete([k, ...Array.from({ length: n }, (_, i) => k + ":" + i)]);
        const rest = list.filter(x => x.id !== m.id); await this.ctx.storage.put("vers", rest);
        this.others(null, { t: "vers", list: rest });
        break;
      }
      case "aw":   // dónde está cada uno (vista, cursor, selección)
        me.aw = m.s ?? null; ws.serializeAttachment(me);
        this.others(ws, { t: "aw", by: me.sid, s: me.aw });
        break;
      case "ping": this.send(ws, { t: "pong" }); break;
    }
  }
  async act(me, e, window) {
    const clip = (v, n) => String(v ?? "").slice(0, n);
    const list = (await this.ctx.storage.get("acts")) || [], now = Date.now(), key = clip(e.key, 120);
    const i = list.findIndex(a => a.key === key && a.by.id === me.id && now - a.at < window);
    const a = { id: i >= 0 ? list[i].id : rnd(6), key, at: now, kind: clip(e.kind, 12), verb: clip(e.verb, 40), label: clip(e.label, 120), snip: clip(e.snip, 160), ref: clip(e.ref, 80), n: i >= 0 ? (list[i].n || 1) + 1 : 1, by: { id: me.id, name: me.name, color: me.color } };
    if (i >= 0) list.splice(i, 1);
    list.unshift(a); await this.ctx.storage.put("acts", list.slice(0, 400));
    this.others(null, { t: "act", a });
  }
  kick(userId) { for (const ws of this.ctx.getWebSockets()) if (ws.deserializeAttachment()?.id === userId) { this.send(ws, { t: "kicked" }); this.bye(ws); } }
  webSocketClose(ws) { this.bye(ws); }
  webSocketError(ws) { this.bye(ws); }
  bye(ws) { try { ws.close(); } catch {} this.others(ws, { t: "users", users: this.users(ws) }); }
}
