from __future__ import annotations


class AutoDevBoundary:
    """Explicit V0.1 boundary. Full AutoDev is intentionally not active yet."""

    def status(self):
        return {
            'ok': True,
            'active': False,
            'phase': 'future-v0.6',
            'reason': 'V0.1 proves the Studio user journey before autonomous editing is enabled.',
        }
