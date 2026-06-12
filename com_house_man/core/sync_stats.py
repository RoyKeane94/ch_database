import logging

from django.core.cache import cache
from django.db.models import Count, Q

from core.models import Company

logger = logging.getLogger(__name__)

SYNC_BAR_BLOCKS = 30
SYNC_STATS_CACHE_KEY = "company_sync_stats"
SYNC_STATS_CACHE_SECONDS = 60


def _aggregate_sync_stats():
    return Company.objects.aggregate(
        total=Count("pk"),
        synced=Count(
            "pk",
            filter=Q(needs_enrichment=False, last_fetched_at__isnull=False),
        ),
        pending=Count("pk", filter=Q(needs_enrichment=True)),
        failed=Count(
            "pk",
            filter=Q(
                needs_enrichment=False,
                last_fetched_at__isnull=True,
            )
            & ~Q(enrichment_error=""),
        ),
    )


def get_sync_stats(*, use_cache=True):
    if use_cache:
        try:
            stats = cache.get(SYNC_STATS_CACHE_KEY)
            if stats is not None:
                return stats
        except Exception:
            logger.warning("Sync stats cache unavailable; querying database directly.")

    stats = _aggregate_sync_stats()
    if use_cache:
        try:
            cache.set(SYNC_STATS_CACHE_KEY, stats, SYNC_STATS_CACHE_SECONDS)
        except Exception:
            logger.warning("Unable to write sync stats to cache.")
    return stats


def invalidate_sync_stats_cache():
    cache.delete(SYNC_STATS_CACHE_KEY)


def sync_stats_payload(stats):
    total = stats["total"]
    synced = stats["synced"]
    failed = stats["failed"]
    percent = round((synced / total) * 100) if total else 0
    filled_blocks = round((synced / total) * SYNC_BAR_BLOCKS) if total else 0
    failed_blocks = round((failed / total) * SYNC_BAR_BLOCKS) if total else 0

    return {
        "total": total,
        "synced": synced,
        "pending": stats["pending"],
        "failed": failed,
        "percent": percent,
        "filled_blocks": filled_blocks,
        "failed_blocks": failed_blocks,
        "block_count": SYNC_BAR_BLOCKS,
    }
