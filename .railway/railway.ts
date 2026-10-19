import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

// This repository owns only its own service in the shared Axelrod project.
export const partial = "world-model";

export default defineRailway((ctx) => {
  if (ctx.environment !== "dev") {
    throw new Error("World Model infrastructure is authorized only for dev.");
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
    source: github("Axelrod-AI-Engineering/world-model", { branch: "main", rootDirectory: ".", checkSuites: false }),
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
      // the scenario the main login opens on (scripts/start-railway.sh reads it); Emily's login opens hers (below)
      WORLD_MODEL_SCENARIO: "prod_demo",
      WORLD_MODEL_REQUIRE_BASIC_AUTH: "1",
      WORLD_MODEL_BASIC_AUTH_USERNAME: preserve(),
      WORLD_MODEL_BASIC_AUTH_PASSWORD: preserve(),
      // logins that open their own scenario, username:password:scenario (api/auth.py); set in Railway only
      WORLD_MODEL_LOGINS: preserve(),
      // the outward API's keys, caller:key:org[:scopes] (api/keys.py, docs/api/README.md); set in Railway only
      WORLD_MODEL_API_KEYS: preserve(),
    },
    networking: {
      serviceDomains: { "world-model-dev.up.railway.app": { port: 8080 } },
    },
    volumeMounts: { "/app/var": storage },
  });
  return project("Axelrod", { resources: [storage, app] });
});
