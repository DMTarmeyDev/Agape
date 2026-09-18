# Agape V3.2 reliability repair

- Source preparation is a background job; browser disconnects reconnect instead of returning Failed to fetch.
- V3.2 uses private bundled service ports: Document Studio 8851 and Workflow Bridge 8852. Legacy R31.10/R2.5 services on 8800/8840 are no longer silently adopted.
- Document creation uses R31.11 asynchronous jobs.
- Transient document/AI timeouts retry up to two times using automatic provider failover.
- Validation repair is only invoked for real validation failures; generic timeouts no longer masquerade as validation-repair failures.
- Core and Work Engine remain shared because the reported installed versions are compatible.
