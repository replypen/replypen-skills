// Cookie consent on vanilla-cookieconsent (assets/vendor/cookieconsent-*), driven by _data/cookies.yml.
// Loaded only when that file lists a category besides "necessary" (_includes/consent.html).
// Recipe: website-dev references/consent.md. Config comes from a JSON block: the CSP forbids inline scripts.
(() => {
  const cfg = JSON.parse(document.getElementById("consent-config").textContent);
  const ids = cfg.categories.map((c) => c.id);

  // Google Consent Mode v2: everything denied until the visitor chooses; set before any Google tag loads.
  const GOOGLE = {
    preferences: ["functionality_storage", "personalization_storage"],
    analytics: ["analytics_storage"],
    marketing: ["ad_storage", "ad_user_data", "ad_personalization"],
  };
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); } // gtag needs the arguments object, not an array
  const googleState = (granted) => {
    const state = {};
    for (const [cat, keys] of Object.entries(GOOGLE)) for (const k of keys) state[k] = granted(cat) ? "granted" : "denied";
    return state;
  };
  gtag("consent", "default", { ...googleState(() => false), security_storage: "granted", wait_for_update: 500 });

  let gtmLoaded = false;
  const loadGtm = () => {
    if (gtmLoaded || !cfg.gtm_id) return;
    gtmLoaded = true;
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    CookieConsent.loadScript(`https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(cfg.gtm_id)}`, { async: "" });
  };
  if (cfg.consent_mode === "advanced") loadGtm();

  const apply = () => {
    const ok = (cat) => CookieConsent.acceptedCategory(cat);
    gtag("consent", "update", googleState(ok));
    // Signal for our own scripts (e.g. the KampAdmin embed): which categories the visitor accepted.
    window.kaConsent = Object.fromEntries(ids.map((id) => [id, ok(id)]));
    document.dispatchEvent(new CustomEvent("ka:consent", { detail: window.kaConsent }));
    if (ok("analytics") || ok("marketing")) loadGtm();
  };

  // "_ga*" in cookies.yml → clear cookies starting with "_ga" when the category is rejected.
  const autoClear = (cat) => ({
    cookies: cfg.cookies.filter((c) => c.category === cat).map((c) =>
      ({ name: c.name.endsWith("*") ? new RegExp(`^${c.name.slice(0, -1).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) : c.name })),
  });
  const categories = Object.fromEntries(cfg.categories.map((c) =>
    [c.id, c.id === "necessary" ? { enabled: true, readOnly: true } : { autoClear: autoClear(c.id) }]));

  const b = cfg.banner;
  const policy = `${b.more_info} <a href="${cfg.policy_url}">${b.policy_link}</a>.`;
  const sections = cfg.categories.map((c) => {
    const rows = cfg.cookies.filter((k) => k.category === c.id);
    return {
      title: c.title,
      description: c.description,
      linkedCategory: c.id,
      ...(rows.length && {
        cookieTable: {
          headers: { name: "Naam", provider: "Van", purpose: "Doel", duration: "Bewaard" },
          body: rows.map(({ name, provider, purpose, duration }) => ({ name, provider, purpose, duration })),
        },
      }),
    };
  });

  CookieConsent.run({
    categories,
    onConsent: apply,
    onChange: apply,
    guiOptions: { consentModal: { layout: "box", position: "bottom left" }, preferencesModal: { layout: "box" } },
    language: {
      default: "nl",
      translations: {
        nl: {
          consentModal: {
            title: b.title,
            description: `${b.text} ${policy}`,
            acceptAllBtn: b.accept_all,
            acceptNecessaryBtn: b.reject_all,
            showPreferencesBtn: b.settings,
          },
          preferencesModal: {
            title: b.settings_title,
            acceptAllBtn: b.accept_all,
            acceptNecessaryBtn: b.reject_all,
            savePreferencesBtn: b.save,
            closeIconLabel: "Sluiten",
            sections: [{ description: policy }, ...sections],
          },
        },
      },
    },
  });
})();
