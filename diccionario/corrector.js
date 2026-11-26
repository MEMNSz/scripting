// Corrector de ortografía (español de Argentina, diccionario RLA-ES es_AR) en un hilo aparte,
// para que cargar el diccionario y buscar sugerencias no frene la escritura.
import NSpell from "./nspell.mjs";
// palabras de uso argentino que el diccionario no trae
const EXTRA = "pibe piba pibes pibas chabón chabona chabones birra birras bondi bondis guita morfar morfi finde findes posta joda jodas bancar banco quilombos boludez boludeces mina minas laburar laburo laburos chamuyo chamuyar fiaca macana macanas yeta pucho puchos trucho trucha truchos changuito bardo bardear garca gil giles cheto cheta chetos careta caretas flashear flash copado copada copados zarpado zarpada mambo mambos pancho panchos facturas medialuna medialunas remis remís colectivo subte".split(" ");
let sp = null;
const ready = (async () => {
  const [aff, dic] = await Promise.all([fetch("es_AR.aff").then(r => r.text()), fetch("es_AR.dic").then(r => r.text())]);
  sp = NSpell(aff, dic);
  for (const w of EXTRA) sp.add(w);
})();
// variantes con tilde / ñ / ü (el error más común), antes que las sugerencias de nspell
const ACC = { a: "á", e: "é", i: "í", o: "ó", u: "úü", n: "ñ" };
function accentFixes(w) {
  const out = new Set(), low = w.toLowerCase(), noAcc = low.normalize("NFD").replace(/[́]/g, "").normalize("NFC");
  const bases = [low, noAcc];
  for (const b of bases) for (let i = 0; i < b.length; i++) for (const r of (ACC[b[i]] || "")) {
    const c = b.slice(0, i) + r + b.slice(i + 1); if (c !== low && sp.correct(c)) out.add(c);
  }
  if (noAcc !== low && sp.correct(noAcc)) out.add(noAcc);
  return [...out];
}
const keepCase = (orig, s) => orig === orig.toUpperCase() ? s.toUpperCase() : orig[0] === orig[0].toUpperCase() ? s[0].toUpperCase() + s.slice(1) : s;
const sugCache = new Map();
onmessage = async e => {
  const { id, op, words, word, add } = e.data;
  try { await ready; } catch (err) { postMessage({ id, error: String(err) }); return; }
  if (op === "check") postMessage({ id, bad: words.filter(w => !sp.correct(w) && !sp.correct(w.toLowerCase())) });
  else if (op === "suggest") {
    if (!sugCache.has(word)) {
      const s = [...new Set([...accentFixes(word), ...sp.suggest(word.toLowerCase())])].slice(0, 6).map(x => keepCase(word, x));
      sugCache.set(word, s);
    }
    postMessage({ id, sug: sugCache.get(word) });
  }
  else if (op === "add") { for (const w of add) sp.add(w); postMessage({ id }); }
};
