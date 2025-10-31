from elasticsearch import Elasticsearch, helpers
from datetime import datetime, date
import sys

# === CONFIGURATION ===
ES_ENDPOINT = "https://my-elasticsearch-project-fb163a.es.asia-south1.gcp.elastic.cloud:443"
ES_API_KEY = "S1BmR0xwb0JyQkNLQWZtRGJnU2U6R082bzl4UmNVWVl6VmpIY2VRYlNQUQ=="

SOURCE_INDEX = "it_asset"
TARGET_INDEX = "it_asset_transformed"

# === CONNECT TO ELASTICSEARCH ===
es = Elasticsearch(
    ES_ENDPOINT,
    api_key=ES_API_KEY,
    verify_certs=True
)

if not es.ping():
    print("❌ Connection failed! Please check endpoint or API key.")
    sys.exit(1)
else:
    print("✅ Connected to Elasticsearch!")


# === HELPER FUNCTIONS ===
def calculate_system_age(install_date):
    """Calculate system age (in years) from installation date."""
    try:
        if not install_date or install_date == "Unknown":
            return None
        install_date = datetime.strptime(install_date, "%Y-%m-%d").date()
        today = date.today()
        years = today.year - install_date.year - (
            (today.month, today.day) < (install_date.month, install_date.day)
        )
        return max(0, years)
    except Exception:
        return None


def get_risk_level(status):
    """Return High if lifecycle status is EOL/EOS, else Low."""
    if not status:
        return "Low"
    status = str(status).strip().upper()
    return "High" if status in ["EOL", "EOS"] else "Low"


def should_delete(doc):
    """Return True if record should be deleted (missing or Unknown hostname)."""
    src = doc.get("_source", {})
    hostname = str(src.get("hostname", "")).strip()
    return not hostname or hostname.lower() == "unknown"


# === MAIN TRANSFORMATION ===
def transform_and_reindex():
    print(f"\n🔄 Reindexing data from '{SOURCE_INDEX}' to '{TARGET_INDEX}'...")

    # Create target index (if not exists)
    if not es.indices.exists(index=TARGET_INDEX):
        es.indices.create(index=TARGET_INDEX)
        print(f"✅ Created target index: {TARGET_INDEX}")

    total = 0
    transformed = 0
    deleted = 0
    actions = []

    for doc in helpers.scan(es, index=SOURCE_INDEX, scroll="5m"):
        total += 1

        if should_delete(doc):
            deleted += 1
            continue

        src = doc["_source"].copy()
        src["risk_level"] = get_risk_level(src.get("operating_system_lifecycle_status"))
        src["system_age_years"] = calculate_system_age(src.get("operating_system_installation_date"))
        src["transformation_timestamp"] = datetime.now().isoformat()

        actions.append({
            "_index": TARGET_INDEX,
            "_source": src
        })
        transformed += 1

    if actions:
        helpers.bulk(es, actions, chunk_size=500)
        print(f"✅ Reindexed {transformed} documents to '{TARGET_INDEX}'")

    print(f"🗑️ Skipped {deleted} invalid documents (missing or Unknown hostnames)")
    print(f"📊 Total processed: {total}")


def update_existing_records():
    """Update existing records in source index using _update_by_query."""
    print(f"\n🔄 Updating '{SOURCE_INDEX}' records with new fields...")

    update_script = {
        "script": {
            "source": """
                String status = ctx._source.operating_system_lifecycle_status;
                if (status != null && (status.equalsIgnoreCase('EOL') || status.equalsIgnoreCase('EOS'))) {
                    ctx._source.risk_level = 'High';
                } else {
                    ctx._source.risk_level = 'Low';
                }

                String dateStr = ctx._source.operating_system_installation_date;
                if (dateStr != null && !dateStr.equalsIgnoreCase('Unknown')) {
                    try {
                        SimpleDateFormat sdf = new SimpleDateFormat('yyyy-MM-dd');
                        Date inst = sdf.parse(dateStr);
                        Date now = new Date();
                        long diff = now.getTime() - inst.getTime();
                        long years = diff / (365L * 24 * 60 * 60 * 1000);
                        ctx._source.system_age_years = (int) Math.max(0, years);
                    } catch (Exception e) {
                        ctx._source.system_age_years = null;
                    }
                }

                ctx._source.last_updated_timestamp = new Date().getTime();
            """,
            "lang": "painless"
        }
    }

    try:
        response = es.update_by_query(
            index=SOURCE_INDEX,
            body=update_script,
            refresh=True,
            wait_for_completion=True
        )

        print(f"✅ Updated {response['updated']} documents in '{SOURCE_INDEX}'")
        if response.get("failures"):
            print(f"⚠️ {len(response['failures'])} update failures detected.")
    except Exception as e:
        print(f"❌ Error updating existing records: {str(e)}")


def delete_invalid_records():
    """Delete records with missing or 'Unknown' hostnames."""
    print(f"\n🗑️ Deleting records with missing or Unknown hostnames from '{SOURCE_INDEX}'...")

    delete_query = {
        "query": {
            "bool": {
                "should": [
                    {"bool": {"must_not": {"exists": {"field": "hostname"}}}},
                    {"term": {"hostname.keyword": ""}},
                    {"term": {"hostname.keyword": "Unknown"}}
                ],
                "minimum_should_match": 1
            }
        }
    }

    try:
        response = es.delete_by_query(
            index=SOURCE_INDEX,
            body=delete_query,
            wait_for_completion=True,
            refresh=True
        )

        print(f"✅ Deleted {response['deleted']} documents with missing/Unknown hostnames.")
        if response.get("failures"):
            print(f"⚠️ {len(response['failures'])} documents failed to delete.")
    except Exception as e:
        print(f"❌ Error deleting invalid hostname records: {str(e)}")


# === MAIN FUNCTION ===
def main():
    print("🚀 Starting Elasticsearch Data Transformation")
    print("=" * 60)

    transform_and_reindex()
    update_existing_records()
    delete_invalid_records()

    print("\n🎯 Transformation completed successfully!")


if __name__ == "__main__":
    main()
