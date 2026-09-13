#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Adapter: Materializes Claude Code events into RDF event graphs.

This module provides the EventAdapter class that converts Claude Code runtime
events (e.g., PostToolUse, SessionStart) into RDF event graphs that can be
merged into the working dataset for knowledge hook execution.
"""

from __future__ import annotations

from typing import Any, Dict
from rdflib import ConjunctiveGraph, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from autofde_lab.ofmf.utils import (
    KH,
    claude_event_to_iri,
    new_graph,
    OFMFError,
    now_ns,
)


class EventAdapter:
    """
    Adapter that materializes Claude Code events into RDF event graphs.
    
    This class converts event names and payloads into RDF graphs that can be
    merged into the working dataset for knowledge hook execution.
    """

    def materialize_event(self, event_name: str, payload: Dict[str, Any]) -> Graph:
        """
        Convert Claude event name and payload into RDF event graph.
        
        Args:
            event_name: Claude event name (e.g., "PostToolUse", "SessionStart")
            payload: Event payload dictionary containing event-specific data
        
        Returns:
            Graph containing RDF triples representing the event
        
        Raises:
            OFMFError: If event_name is not recognized
        """
        # Map event name to IRI
        event_iri = claude_event_to_iri(event_name)
        
        # Create event graph
        event_g = new_graph()
        event_g.bind("kh", KH)
        
        # Create event instance IRI (deterministic based on event name and payload)
        # For now, use a simple hash-based approach
        import hashlib
        payload_str = str(sorted(payload.items()))
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
        event_instance_iri = URIRef(f"urn:event:{event_name.lower()}:{payload_hash}")
        
        # Add event type
        event_g.add((event_instance_iri, RDF.type, event_iri))
        
        # Add event metadata from payload
        if "eventId" in payload:
            event_g.add((event_instance_iri, KH.eventId, Literal(payload["eventId"])))
        
        if "sessionId" in payload:
            event_g.add((event_instance_iri, KH.sessionId, Literal(payload["sessionId"])))
        
        if "turnId" in payload:
            event_g.add((event_instance_iri, KH.turnId, Literal(payload["turnId"])))
        
        # Add tool-specific metadata for tool events
        if event_name in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            if "toolName" in payload:
                event_g.add((event_instance_iri, KH.toolName, Literal(payload["toolName"])))
            
            if "toolArgs" in payload:
                # Tool args can be a dict or JSON string
                import json
                if isinstance(payload["toolArgs"], dict):
                    args_str = json.dumps(payload["toolArgs"], sort_keys=True)
                else:
                    args_str = str(payload["toolArgs"])
                event_g.add((event_instance_iri, KH.toolArgs, Literal(args_str)))
            
            if "toolResult" in payload and event_name == "PostToolUse":
                # Tool result can be complex - store as JSON string for now
                import json
                if isinstance(payload["toolResult"], dict):
                    result_str = json.dumps(payload["toolResult"], sort_keys=True)
                else:
                    result_str = str(payload["toolResult"])
                event_g.add((event_instance_iri, KH.toolResult, Literal(result_str)))
        
        # Add timestamp (non-hashed metadata)
        from specify_cli.kgc_ofmf_utils import now_ns
        event_g.add((event_instance_iri, KH.timestampNs, Literal(now_ns(), datatype=XSD.integer)))
        
        return event_g

    def merge_event_into_state(
        self, event_graph: Graph, state: ConjunctiveGraph
    ) -> None:
        """
        Merge event graph into working dataset state.
        
        Args:
            event_graph: Graph containing event triples
            state: Working dataset to merge event into
        """
        # Add all triples from event graph to default context of state
        for s, p, o in event_graph.triples((None, None, None)):
            state.add((s, p, o))
