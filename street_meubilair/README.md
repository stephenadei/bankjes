# Amsterdam Street Furniture Explorer

A Frappe application that ingests and visualizes street furniture data from Amsterdam's open data APIs.

## Features

- **Data Ingestion**: Automatically syncs data from 5 Amsterdam open data sources covering >95% of street furniture
- **Interactive Map**: Leaflet-based map with clustering and filtering capabilities
- **REST API**: Nearby furniture search using Haversine distance calculation
- **Automated Sync**: Daily scheduled synchronization of data

## Data Sources

| Dataset | Description | API Endpoint |
|---------|-------------|--------------|
| BRT10 | Benches, picnic tables, trash bins | `api.data.amsterdam.nl/v1/brt10/inrichtingselementen/` |
| Household Waste | Underground/overground waste containers | `api.data.amsterdam.nl/v1/huishoudelijkafval/containerlocatie/` |
| Public Lighting | Light poles and status information | `api.data.amsterdam.nl/v1/storingsmeldingen_openbare_verlichting_en_klokken/openbareVerlichting/` |
| Bike Poles | Protective and parking pole information | `api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/` |
| Sports | Benches and seating at playgrounds | `api.data.amsterdam.nl/v1/sport/openbaresportplek/` |

## Installation

### Prerequisites

- Python 3.11+
- Frappe Framework v15
- Docker (optional)

### Docker Setup

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd street_meubilair
   ```

2. Start with Docker Compose:
   ```bash
   docker compose up -d
   ```

3. Create a new site:
   ```bash
   bench new-site ams.local --admin-password=admin
   ```

4. Install the app:
   ```bash
   bench --site ams.local install-app street_meubilair
   ```

5. Start the development server:
   ```bash
   bench start
   ```

### Manual Setup

1. Install Frappe Framework following [official documentation](https://frappeframework.com/docs/user/en/installation)

2. Clone this app into your apps directory:
   ```bash
   cd frappe-bench/apps
   git clone <repo-url> street_meubilair
   ```

3. Install the app:
   ```bash
   bench --site your-site install-app street_meubilair
   ```

## Usage

### Accessing the Map

Visit `/kaart` on your site to view the interactive map of Amsterdam street furniture.

### API Endpoints

#### Get Nearby Furniture
```
GET /api/method/street_meubilair.api.furniture_nearby
```

Parameters:
- `lat` (required): Latitude
- `lon` (required): Longitude  
- `radius` (optional): Search radius in kilometers (default: 1)
- `type` (optional): Filter by furniture type

Example:
```bash
curl "http://your-site/api/method/street_meubilair.api.furniture_nearby?lat=52.3676&lon=4.9041&radius=0.5"
```

### Manual Data Sync

To manually trigger data synchronization:

```python
import frappe
frappe.get_attr("street_meubilair.sync_all.sync")()
```

## Configuration

### API Key Setup

When Amsterdam's Data Service Platform requires API keys:

```bash
bench set-config datapunt_api_key your_api_key_here
```

## Testing

Run tests using:

```bash
bench --site your-site run-tests --app street_meubilair
```

## Architecture

### DocTypes

- **Street Furniture Type**: Categories of furniture (Bank, Prullenbak, etc.)
- **Street Furniture Item**: Individual furniture items with location and metadata
- **Sync Log**: Tracks synchronization history and status

### Scheduled Jobs

- Daily sync of all data sources
- Automatic conflict resolution for duplicate entries

## Development

### Adding New Data Sources

1. Add the new dataset to `TABLES` in `sync_all.py`
2. Update field mappings if needed
3. Add any specific filters for the dataset

### Customizing the Map

The map template is located at `templates/pages/kaart.html`. Customize:
- Map styling and layers
- Marker icons and clustering
- Filter options
- Popup content

## Roadmap

- [ ] PWA / offline tiles support
- [ ] User photo upload for reporting broken furniture
- [ ] WebSocket push notifications for status updates
- [ ] Prometheus metrics for monitoring sync performance
- [ ] Multi-language support
- [ ] Mobile app development

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Data Attribution

Data provided by [Gemeente Amsterdam](https://data.amsterdam.nl/) under open data license. 