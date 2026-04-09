# BudgetBakers Wallet

## Published MQTT topics

- `<prefix>/status/state`
- `<prefix>/status/attributes`
- `<prefix>/last_sync`
- `<prefix>/accounts/raw`
- `<prefix>/accounts/summary`
- `<prefix>/transactions/recent/raw`
- `<prefix>/transactions/recent/summary`
- `<prefix>/command/sync`

Publishing `now` to `<prefix>/command/sync` triggers an immediate refresh.

## Suggested publish config

```yaml
publish:
  - accounts
  - recent_transactions
  - status
```

## Limitation

This add-on does not currently create balance entities because the live Wallet account payloads checked during development did not consistently expose a usable current balance field.
