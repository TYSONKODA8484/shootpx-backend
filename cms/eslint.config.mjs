import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextVitals,
  {
    ignores: [".next/**", "node_modules/**"],
  },
  {
    rules: {
      // eslint-plugin-react-hooks v7 ships React Compiler-oriented rules as
      // hard errors. set-state-in-effect flags the standard "fetch on
      // mount/param change, setState in a cancellable effect" pattern used
      // throughout this app's data-fetching (see EntityForm.tsx, the entity
      // list page) — an accepted use of effects per React's own docs, which
      // this static rule can't distinguish from a real derived-state
      // anti-pattern. Keep it visible as a warning rather than silencing it.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default config;
