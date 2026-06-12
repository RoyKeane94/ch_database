from core.sync_stats import get_sync_stats, sync_stats_payload


def teletext_context(request):
    stats = sync_stats_payload(get_sync_stats())
    return {
        "tt_total_companies": stats["total"],
        "tt_sync_status": stats,
    }
