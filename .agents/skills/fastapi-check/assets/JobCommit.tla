----------------------------- MODULE JobCommit -----------------------------
EXTENDS Naturals, FiniteSets

CONSTANTS Workers, MaxAttempts, ProtectAttempt
VARIABLES phase, attempt, tickets, commits, staleCommit

vars == <<phase, attempt, tickets, commits, staleCommit>>

Init ==
    /\ phase = "queued"
    /\ attempt = 0
    /\ tickets = [worker \in 1..Workers |-> 0]
    /\ commits = 0
    /\ staleCommit = FALSE

Claim(worker) ==
    /\ phase \in {"queued", "waiting_retry"}
    /\ attempt < MaxAttempts
    /\ attempt' = attempt + 1
    /\ tickets' = [tickets EXCEPT ![worker] = attempt + 1]
    /\ phase' = "running"
    /\ UNCHANGED <<commits, staleCommit>>

Reclaim ==
    /\ phase = "running"
    /\ phase' = "waiting_retry"
    /\ UNCHANGED <<attempt, tickets, commits, staleCommit>>

Commit(worker) ==
    /\ phase = "running"
    /\ tickets[worker] > 0
    /\ (~ProtectAttempt \/ tickets[worker] = attempt)
    /\ phase' = "done"
    /\ commits' = commits + 1
    /\ staleCommit' = (staleCommit \/ (tickets[worker] # attempt))
    /\ UNCHANGED <<attempt, tickets>>

Next == Reclaim \/
    (\E worker \in 1..Workers : Claim(worker) \/ Commit(worker))

TypeOK ==
    /\ phase \in {"queued", "running", "waiting_retry", "done"}
    /\ attempt \in 0..MaxAttempts
    /\ tickets \in [1..Workers -> 0..MaxAttempts]
    /\ commits \in Nat
    /\ staleCommit \in BOOLEAN

CurrentAttemptOnly == ~staleCommit
AtMostOneCommit == commits <= 1

Spec == Init /\ [][Next]_vars
=============================================================================
