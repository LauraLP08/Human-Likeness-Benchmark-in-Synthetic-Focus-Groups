import re
from typing import Dict, Any, List, Tuple
from .schema import SessionArtifacts, TrackResult, MetricResult, Flag
from .flags import apply_track_status_from_flags

def build_interaction_graph(artifacts: SessionArtifacts) -> Tuple[TrackResult, List[Dict[str, str]]]:
    track = TrackResult(track_id="interaction_graph")
    edges = []
    
    if not artifacts.transcript:
        track.status = "BLOCKED"
        return track, edges
        
    participant_names = {u.get("speaker_id"): u.get("speaker_name") for u in artifacts.transcript if u.get("speaker_role") != "moderator" and u.get("speaker_id") != "MODERATOR"}
    
    first_name_match_count = 0
    full_name_match_count = 0
    
    for i, t in enumerate(artifacts.transcript):
        speaker = t.get("speaker_id")
        role = t.get("speaker_role")
        content = t.get("content", "").lower()
        
        if role == "moderator" or speaker == "MODERATOR":
            for p_id, p_name in participant_names.items():
                if not p_name: continue
                p_name_lower = p_name.lower()
                first_name = p_name_lower.split()[0]
                
                matched = False
                if p_name_lower in content:
                    matched = True
                    full_name_match_count += 1
                elif len(first_name) > 2 and re.search(rf'\b{re.escape(first_name)}\b', content):
                    matched = True
                    first_name_match_count += 1
                elif p_id.lower() in content:
                    matched = True
                    
                if matched:
                    edges.append({"source": "MODERATOR", "target": p_id, "type": "addressed"})
        else:
            prev_speaker = artifacts.transcript[i-1].get("speaker_id") if i > 0 else None
            prev_role = artifacts.transcript[i-1].get("speaker_role") if i > 0 else None
            if prev_role == "moderator" or prev_speaker == "MODERATOR":
                edges.append({"source": speaker, "target": "MODERATOR", "type": "answered"})
            elif prev_speaker and prev_speaker != speaker:
                # Adjacent participant uptake
                edges.append({"source": speaker, "target": prev_speaker, "type": "adjacent_uptake"})
                
            for p_id, p_name in participant_names.items():
                if p_id == speaker: continue
                if not p_name: continue
                
                p_name_lower = p_name.lower()
                first_name = p_name_lower.split()[0]
                
                matched = False
                if p_name_lower in content:
                    matched = True
                    full_name_match_count += 1
                elif len(first_name) > 2 and re.search(rf'\b{re.escape(first_name)}\b', content):
                    matched = True
                    first_name_match_count += 1
                elif p_id.lower() in content:
                    matched = True
                    
                if matched:
                    edges.append({"source": speaker, "target": p_id, "type": "referenced"})
                    
    track.metrics["total_edges"] = MetricResult("total_edges", len(edges))
    
    p2p_edges = [e for e in edges if e["source"] != "MODERATOR" and e["target"] != "MODERATOR"]
    m2p_edges = [e for e in edges if e["source"] == "MODERATOR"]
    p2m_edges = [e for e in edges if e["target"] == "MODERATOR"]
    
    n_parts = len(participant_names)
    p2p_density = 0.0
    max_p2p = 0
    unique_p2p = 0
    
    if n_parts > 1:
        max_p2p = n_parts * (n_parts - 1)
        # Here we just count unique pairs (directed)
        unique_p2p = len(set((e["source"], e["target"]) for e in p2p_edges))
        p2p_density = unique_p2p / max_p2p
    else:
        # Handle INSUFFICIENT_SAMPLE safely via metric object
        pass
    
    # Simple derivation for mod-participant density
    max_m2p = n_parts
    unique_m2p = len(set((e["source"], e["target"]) for e in m2p_edges))
    m2p_density = unique_m2p / max_m2p if max_m2p > 0 else 0.0
    
    max_p2m = n_parts
    unique_p2m = len(set((e["source"], e["target"]) for e in p2m_edges))
    p2m_density = unique_p2m / max_p2m if max_p2m > 0 else 0.0
    
    m_p2p_density = MetricResult("participant_to_participant_edge_density", p2p_density)
    if n_parts < 2:
        m_p2p_density.status = "INSUFFICIENT_SAMPLE"
        
    track.metrics["participant_to_participant_edge_count"] = MetricResult("participant_to_participant_edge_count", len(p2p_edges))
    track.metrics["participant_to_participant_unique_edge_count"] = MetricResult("participant_to_participant_unique_edge_count", unique_p2p)
    track.metrics["participant_to_participant_possible_directed_edges"] = MetricResult("participant_to_participant_possible_directed_edges", max_p2p)
    track.metrics["participant_to_participant_edge_density"] = m_p2p_density
    
    track.metrics["moderator_to_participant_edge_count"] = MetricResult("moderator_to_participant_edge_count", len(m2p_edges))
    track.metrics["moderator_to_participant_edge_density"] = MetricResult("moderator_to_participant_edge_density", m2p_density)
    track.metrics["participant_to_moderator_edge_count"] = MetricResult("participant_to_moderator_edge_count", len(p2m_edges))
    track.metrics["participant_to_moderator_edge_density"] = MetricResult("participant_to_moderator_edge_density", p2m_density)
    
    track.metrics["first_name_match_count"] = MetricResult("first_name_match_count", first_name_match_count)
    track.metrics["full_name_match_count"] = MetricResult("full_name_match_count", full_name_match_count)
    
    if len(p2p_edges) == 0 and len(m2p_edges) > 5:
        track.flags.append(Flag("HUB_AND_SPOKE", "warning", "interaction_graph", "No participant-to-participant edges found; conversation is entirely hub-and-spoke via moderator."))
        
    return apply_track_status_from_flags(track), edges
