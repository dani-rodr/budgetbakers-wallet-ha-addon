# BudgetBakers Wallet

A lightweight Home Assistant add-on that polls the BudgetBakers Wallet REST API and publishes Wallet data through MQTT auto-discovery.

## Features

- MQTT auto-discovery for core status entities
- Manual **Sync Now** button entity for on-demand refresh
- Configurable polling interval
- Configurable publish scope
- Raw retained MQTT topics for accounts and recent transactions

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `wallet_token` | required | BudgetBakers Wallet REST token |
| `poll_interval_minutes` | `15` | Minutes between background refreshes |
| `mqtt_topic_prefix` | `wallet_budgetbakers` | Base MQTT topic prefix |
| `recent_transactions_limit` | `10` | Number of recent transactions to publish |
| `publish` | `accounts,recent_transactions,status` | Select which datasets are published |
| `log_level` | `info` | Logging level |

## Entities

- `Last Sync`
- `API Status`
- `Accounts Count`
- `Recent Transactions`
- `Sync Now` button

## Notes

- MQTT connection settings are resolved automatically from Home Assistant Supervisor.
- The add-on publishes recent transactions and account metadata. The Wallet `accounts` responses observed so far did not reliably expose live account balances, so balance sensors are intentionally not created yet.
