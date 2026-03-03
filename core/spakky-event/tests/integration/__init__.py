"""Integration tests for spakky-event package.

Tests the full event publishing flow:
TransactionalEventPublishingAspect → DomainEventPublisher → DomainEventMediator → @EventHandler
"""
