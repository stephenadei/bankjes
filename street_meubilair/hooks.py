
app_name = "street_meubilair"
app_title = "Stephen's Bankjes"
app_publisher = "Stephen"
app_description = "Stephen's Amsterdam Bankjes (Benches) Explorer"
app_email = "your@email.com"
app_license = "MIT"

scheduler_events = {
    "daily": [
        "street_meubilair.sync_all.sync"
    ]
}

override_whitelisted_methods = {
    "street_meubilair.api.furniture_nearby": "street_meubilair.api.furniture_nearby"
} 