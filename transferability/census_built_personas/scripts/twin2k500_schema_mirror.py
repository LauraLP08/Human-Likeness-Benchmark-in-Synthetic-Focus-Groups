"""
Local Pydantic mirror of ARCHITECTURE.md Appendix B agent JSON schema.

USED ONLY for validating ETL output in this folder. NOT imported by core/.
If Appendix B changes, update this file by hand.
"""
from typing import Any

from pydantic import BaseModel, Field


class Location(BaseModel):
    region: str | None = None
    country: str | None = None
    urban_rural: str | None = None


class Demographics(BaseModel):
    name: str
    age: int
    age_bucket: str | None = None
    gender: str
    location: Location | None = None
    diet: str | None = None


class Persona(BaseModel):
    demographics: Demographics
    food_consumption: dict[str, Any] | None = None
    psychological_profile: dict[str, Any] | None = None


class SimulationConfig(BaseModel):
    temperature: float | None = None
    model: str | None = None
    max_tokens: int | None = None
    notes: str | None = None


class AgentPayload(BaseModel):
    agent_id: str = Field(..., min_length=1)
    version: int | None = None
    tier: str | None = None
    created_at: str | None = None
    persona: Persona
    simulation_config: SimulationConfig | None = None
