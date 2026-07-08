# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from unittest import mock


def test_cache_channels_clears_stale_continuation_cursor_after_full_crawl(
    mocker,
) -> None:
    """
    A full Celery crawl must clear any stale continuation cursor left behind
    by an earlier partial self-seed (from a synchronous cache-miss request) -
    otherwise it lingers and is misread as "the cache is still truncated"
    against a now-complete cache, triggering a spurious live API call.
    """
    from superset.tasks.slack import cache_channels
    from superset.utils.slack import (
        SLACK_CHANNELS_CACHE_KEY,
        SLACK_CHANNELS_CONTINUATION_CURSOR_KEY,
    )

    mock_app = mock.MagicMock()
    mock_app.config = {
        "SLACK_ENABLE_CACHING": True,
        "SLACK_CACHE_TIMEOUT": 86400,
        "SLACK_API_RATE_LIMIT_RETRY_COUNT": 2,
    }
    mocker.patch("superset.tasks.slack.current_app", mock_app)

    mocker.patch(
        "superset.tasks.slack.get_channels_with_search",
        side_effect=[
            {
                "result": [{"id": "C1", "name": "general"}],
                "next_cursor": "page2",
                "has_more": True,
            },
            {
                "result": [{"id": "C2", "name": "random"}],
                "next_cursor": None,
                "has_more": False,
            },
        ],
    )

    mock_cache = mocker.patch("superset.tasks.slack.cache_manager")

    cache_channels()

    mock_cache.cache.set.assert_called_once()
    assert mock_cache.cache.set.call_args.args[0] == SLACK_CHANNELS_CACHE_KEY
    mock_cache.cache.delete.assert_called_once_with(
        SLACK_CHANNELS_CONTINUATION_CURSOR_KEY
    )
