import { defineRailway, preserve, project, service, volume } from "railway/iac";

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
      WORLD_MODEL_REQUIRE_BASIC_AUTH: "1",
      WORLD_MODEL_BASIC_AUTH_USERNAME: preserve(),
      WORLD_MODEL_BASIC_AUTH_PASSWORD: preserve(),
    },
    volumeMounts: { "/app/var": storage },
  });
  return project("Axelrod", { resources: [storage, app] });
});
