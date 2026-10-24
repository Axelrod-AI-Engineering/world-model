import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

// This repository owns only its own services in the shared Axelrod project (docs/deployment.md#three-services):
//   world-model            the model API and UI                      dev only
//   world-model-ingestion  parsing, embedding, extraction            dev only
//   world-model-data       the lakehouse: SQLite file and raw files  production only
// Dev, staging, and prod all reach the one data service through its public URL and token, with organizations as tenants,
// so the data lives in one place and no environment holds a copy of it.
export const partial = "world-model";

const repo = github("Axelrod-AI-Engineering/world-model", { branch: "main", rootDirectory: ".", checkSuites: false });

export default defineRailway((ctx) => {
  // The guard, by environment. The data service is the only resource allowed in production: it is where the one lake
  // lives, and the world model and ingestion never run there (they stay dev-only until they are authorized elsewhere).
  if (ctx.environment === "production") return dataService();
  if (ctx.environment !== "dev") {
    throw new Error("World Model infrastructure is authorized only for dev, and the data service for production.");
  }
  const storage = volume("world-model-volume", {
    sizeMB: 5000,
    region: "us-west2",
    allowOnlineResize: true,
  });
  const app = service("world-model", {
    root: ".",
    // Railway builds and deploys every push to main from this repository (Oct 11). Declared here so an apply keeps
    // the link instead of removing it.
    source: repo,
    // The watch patterns (railway.json at the root) are every path this image copies; a change under ingestion/ redeploys
    // all three services, one under world_model/ only this one.
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: {
      healthcheckPath: "/api/health",
      // First startup builds three years of synthetic history.
      healthcheckTimeout: 600,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 2,
      sleepApplication: false,
      multiRegionConfig: { "us-west2": { numReplicas: 1 } },
      ipv6EgressEnabled: false,
    },
    variables: {
      PORT: "8080",
      // the scenario the main login opens on (.railway/start-railway.sh reads it); Emily's login opens hers (below)
      WORLD_MODEL_SCENARIO: "prod_demo",
      // client scenarios, worlds, and configs are never in the image or the repository: they are loaded from the
      // volume (world_model/src/axelrod_wm/clients.py, docs/deployment.md#client-content)
      WORLD_MODEL_CLIENT_DIR: "/app/var/clients",
      WORLD_MODEL_REQUIRE_BASIC_AUTH: "1",
      WORLD_MODEL_BASIC_AUTH_USERNAME: preserve(),
      WORLD_MODEL_BASIC_AUTH_PASSWORD: preserve(),
      // logins that open their own scenario, username:password:scenario (api/auth.py); set in Railway only
      WORLD_MODEL_LOGINS: preserve(),
      // the outward API's keys, caller:key:org[:scopes] (api/keys.py, world_model/docs/api/README.md). The secrets above come from
      // the gitignored .creds.dev through .railway/railway-sync-creds.sh; non-secret settings (trusted core issuers,
      // owners, compartments) are checked in at configs/world_model.dev.toml (world_model/src/axelrod_wm/settings.py).
      WORLD_MODEL_API_KEYS: preserve(),
      // the data and ingestion services (set in Railway only; with the URLs unset this process runs the lake and the
      // pipeline in process, as before). The lake is the production data service's public URL; ingestion is reached on
      // the private network (world-model-ingestion.railway.internal) and needs the lake too.
      WORLD_MODEL_LAKE_URL: preserve(),
      WORLD_MODEL_LAKE_TOKEN: preserve(),
      WORLD_MODEL_INGEST_URL: preserve(),
      WORLD_MODEL_INGEST_TOKEN: preserve(),
    },
    networking: {
      serviceDomains: { "world-model-dev.up.railway.app": { port: 8080 } },
    },
    volumeMounts: { "/app/var": storage },
  });
  const ingestion = service("world-model-ingestion", {
    root: ".",
    source: repo,
    // Stateless: no volume. File bytes are held in memory while a document is processed, and the OCR page cache and the
    // embedding weights are in temporary storage. Private network only: no public domain.
    build: { builder: "DOCKERFILE", dockerfilePath: "ingestion/Dockerfile" },
    deploy: {
      healthcheckPath: "/health",
      healthcheckTimeout: 300,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 2,
      sleepApplication: false,
      multiRegionConfig: { "us-west2": { numReplicas: 1 } },
      ipv6EgressEnabled: false,
    },
    variables: {
      PORT: "8080",
      INGEST_TOKEN: preserve(),
      // the data service (public URL, production) and its token
      WORLD_MODEL_LAKE_URL: preserve(),
      WORLD_MODEL_LAKE_TOKEN: preserve(),
      // the optional LLM step (ingestion/docs/pipeline.md): provider, model, and key, when it is switched on
      WORLD_MODEL_LLM_PROVIDER: preserve(),
      WORLD_MODEL_LLM_MODEL: preserve(),
      ANTHROPIC_API_KEY: preserve(),
    },
  });
  return project("Axelrod", { resources: [storage, app, ingestion] });
});

// Production: the data service and its volume, and nothing else.
function dataService() {
  const lake = volume("world-model-data-volume", {
    sizeMB: 5000,
    region: "us-west2",
    allowOnlineResize: true,
  });
  const data = service("world-model-data", {
    root: ".",
    source: repo,
    build: { builder: "DOCKERFILE", dockerfilePath: "ingestion/Dockerfile.lake" },
    deploy: {
      healthcheckPath: "/health",
      healthcheckTimeout: 120,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 2,
      sleepApplication: false,
      // one replica: this process is the only one that opens the SQLite file
      multiRegionConfig: { "us-west2": { numReplicas: 1 } },
      ipv6EgressEnabled: false,
    },
    variables: {
      PORT: "8080",
      LAKE_DIR: "/data/lake",
      LAKE_TOKEN: preserve(),
    },
    // dev, staging, and prod reach it here, with the token
    networking: {
      serviceDomains: { "world-model-data.up.railway.app": { port: 8080 } },
    },
    volumeMounts: { "/data": lake },
  });
  return project("Axelrod", { resources: [lake, data] });
}
