from collections import deque
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class State:
    phase: str = "queued"
    attempt: int = 0
    tickets: tuple[int, int] = (0, 0)
    commits: int = 0


def transitions(state: State, *, fenced: bool) -> list[tuple[str, State, bool]]:
    found = []
    for worker, ticket in enumerate(state.tickets):
        if state.phase in ("queued", "waiting_retry") and state.attempt < 2:
            attempt = state.attempt + 1
            tickets = tuple(
                attempt if index == worker else old for index, old in enumerate(state.tickets)
            )
            next_state = State("running", attempt, (tickets[0], tickets[1]), state.commits)
            found.append((f"worker{worker + 1} claim attempt{attempt}", next_state, True))
        if state.phase == "running" and ticket and (not fenced or ticket == state.attempt):
            next_state = replace(state, phase="done", commits=state.commits + 1)
            found.append(
                (f"worker{worker + 1} commit attempt{ticket}", next_state, ticket == state.attempt)
            )
    if state.phase == "running":
        found.append(("lease expired and reclaimed", replace(state, phase="waiting_retry"), True))
    return found


def explore(*, fenced: bool) -> tuple[int, list[str]]:
    initial = State()
    queue: deque[tuple[State, list[str]]] = deque([(initial, [])])
    seen = {initial}
    while queue:
        state, path = queue.popleft()
        for action, target, owned in transitions(state, fenced=fenced):
            trace = [*path, action]
            if not owned or target.commits > 1:
                return len(seen), trace
            if target not in seen:
                seen.add(target)
                queue.append((target, trace))
    return len(seen), []
