# Keycloak realm for the `oidc` compose profile (local testing only)

`smriti-realm.json` is imported by `docker compose --profile oidc up`. It defines the realm
`smriti` with SMRITI's six roles as realm roles, a **public** client `smriti-web`
(authorisation code + PKCE S256 only; no implicit flow, no password grant) whose tokens carry
`aud: smriti-web`, and four demo users:

| User | Role |
|---|---|
| `priya` | rtmac_engineer |
| `arun` | drilling_engineer |
| `meera` | viewer |
| `kc-admin` | admin |

All four share the password `smriti-demo-password`. **This realm is for local and CI testing
only:** never import it into an identity provider that anyone else uses. At Oil India the
realm (or Entra ID / another provider) is configured by their IAM team; SMRITI only needs the
issuer, the client id and the claim that carries roles (`SMRITI_OIDC_*`, BACKEND_PLAN §7).
