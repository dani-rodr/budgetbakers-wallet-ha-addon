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

## Balance overrides

If Wallet's public API does not reconcile an account's current balance correctly, you can provide a known balance and timestamp in the add-on config.

```yaml
balance_overrides:
  - account_name: BPI
    starting_balance: 285000
    as_of: "2026-03-26T02:56:47Z"
  - account_name: Metrobank
    starting_balance: 200000
    as_of: "2026-02-13T16:08:57Z"
  - account_name: Cash
    starting_balance: 0
    as_of: "2026-02-26T13:40:25Z"
```

The add-on treats each override as the correct balance after all transactions up to `as_of`, then applies only records after that timestamp.

## Limitation

This add-on does not currently create balance entities because the live Wallet account payloads checked during development did not consistently expose a usable current balance field.
