// Cloudflare Pages 24x7 Serverless FreeLLMAPI Edge Gateway + Static Asset Router
const GATEWAY_TOKEN = "freellmapi-ceb04983702628b4439a5a1d9e9bf34484f948c29dbe8b4f";

const UPSTREAM_ROUTES = [
  { provider: "ovh", model: "Qwen2.5-VL-72B-Instruct", url: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions" },
  { provider: "ovh", model: "Mistral-Small-3.2-24B-Instruct-2506", url: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions" },
  { provider: "ovh", model: "gpt-oss-120b", url: "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions" },
  { provider: "kilo", model: "cohere/north-mini-code:free", url: "https://api.kilo.ai/api/gateway/v1/chat/completions" },
  { provider: "kilo", model: "nvidia/nemotron-3.5-lightning:free", url: "https://api.kilo.ai/api/gateway/v1/chat/completions" }
];

function checkAuth(request) {
  const auth = (request.headers.get("Authorization") || "").trim();
  return auth === `Bearer ${GATEWAY_TOKEN}` || auth === GATEWAY_TOKEN;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.loanraaj.com") {
      url.hostname = "loanraaj.com";
      return Response.redirect(url.toString(), 301);
    }

    if (url.pathname === "/v1/models" && request.method === "GET") {
      if (!checkAuth(request)) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
      const data = UPSTREAM_ROUTES.map((r) => ({
        id: r.model,
        object: "model",
        owned_by: r.provider,
        edge_gateway: "cloudflare-24x7"
      }));
      data.unshift({ id: "auto", object: "model", owned_by: "freellmapi-edge", edge_gateway: "cloudflare-24x7" });
      return new Response(JSON.stringify({ object: "list", data }), {
        status: 200,
        headers: { "Content-Type": "application/json", "X-Edge-Gateway": "cloudflare-loanraaj-24x7" }
      });
    }

    if (url.pathname === "/v1/chat/completions" && request.method === "POST") {
      if (!checkAuth(request)) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return new Response(JSON.stringify({ error: "Invalid JSON body" }), { status: 400, headers: { "Content-Type": "application/json" } });
      }

      const requestedModel = (body.model || "auto").trim();
      const ordered = [];
      for (const r of UPSTREAM_ROUTES) {
        if (r.model === requestedModel) ordered.push(r);
      }
      for (const r of UPSTREAM_ROUTES) {
        if (!ordered.includes(r)) ordered.push(r);
      }

      const errors = [];
      for (const route of ordered) {
        try {
          const upstreamPayload = {
            model: route.model,
            messages: body.messages || [],
            max_tokens: body.max_tokens || 2500,
            temperature: typeof body.temperature === "number" ? body.temperature : 0.7
          };
          const resp = await fetch(route.url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "User-Agent": "Mozilla/5.0 FreeLLMAPI-Cloudflare-Edge/2.0"
            },
            body: JSON.stringify(upstreamPayload)
          });
          if (resp.ok) {
            const data = await resp.json();
            const choice = (data.choices && data.choices[0]) || {};
            const msg = choice.message || {};
            const text = (msg.content || msg.reasoning_content || msg.reasoning || "").trim();
            if (text.length > 0) {
              if (!msg.content) {
                data.choices[0].message.content = text;
              }
              return new Response(JSON.stringify(data), {
                status: 200,
                headers: {
                  "Content-Type": "application/json",
                  "X-Edge-Gateway": "cloudflare-loanraaj-24x7",
                  "X-Served-Provider": route.provider,
                  "X-Served-Model": route.model
                }
              });
            }
          } else {
            errors.push(`${route.provider}/${route.model}:HTTP_${resp.status}`);
          }
        } catch (err) {
          errors.push(`${route.provider}/${route.model}:${err.message}`);
        }
      }

      return new Response(JSON.stringify({ error: "All upstream providers failed", details: errors }), {
        status: 502,
        headers: { "Content-Type": "application/json", "X-Edge-Gateway": "cloudflare-loanraaj-24x7" }
      });
    }

    return env.ASSETS.fetch(request);
  }
};
