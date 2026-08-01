#!/usr/bin/env bash
# jq definitions shared by comment collection and monitor state snapshots.

INFORMATIONAL_BOT_FILTER='
  def informational_bot:
    (.user.login // "") | test("^(codecov|linear)(\\[bot\\])?$");
'
