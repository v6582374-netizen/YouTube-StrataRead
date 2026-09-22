"""External YouTube player-page fixtures shared by isolated integration tests."""

import json


class RegularVideos:
    def classify(self, video_id, **_kwargs):
        return False


def player_page(video_id, is_short, *, status="OK", canonical=None):
    path = f"shorts/{video_id}" if is_short is True else f"watch?v={video_id}"
    canonical = canonical or f"https://www.youtube.com/{path}"
    player = {
        "playabilityStatus": {"status": status},
        "videoDetails": {"videoId": video_id, "lengthSeconds": "120"},
        "microformat": {
            "playerMicroformatRenderer": {
                "externalVideoId": video_id,
                "isShortsEligible": is_short,
            }
        },
    }
    return f'<html><link rel="canonical" href="{canonical}"><script>var ytInitialPlayerResponse = {json.dumps(player)};</script></html>'
