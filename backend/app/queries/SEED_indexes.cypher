// Range indexes on stable application ids (statements separated by ';').
// An index speeds lookups only; it is NOT a uniqueness constraint (GRAPH_MODEL).
CREATE INDEX FOR (n:Workspace) ON (n.id);
CREATE INDEX FOR (n:Brand) ON (n.id);
CREATE INDEX FOR (n:Campaign) ON (n.id);
CREATE INDEX FOR (n:Creator) ON (n.id);
CREATE INDEX FOR (n:Offer) ON (n.id);
CREATE INDEX FOR (n:Availability) ON (n.id);
CREATE INDEX FOR (n:Agreement) ON (n.id);
CREATE INDEX FOR (n:Audit) ON (n.id);
CREATE INDEX FOR (n:Source) ON (n.id);
CREATE INDEX FOR (n:Session) ON (n.id);
CREATE INDEX FOR (n:Message) ON (n.id);
CREATE INDEX FOR (n:Run) ON (n.id);
CREATE INDEX FOR (n:Proposal) ON (n.id);
CREATE INDEX FOR (n:Decision) ON (n.id);
CREATE INDEX FOR (n:MutationReceipt) ON (n.id)
