"""OpenAPI contract for the generic Event Daemon HTTP surface."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_JSON = {"application/json": {"schema": {}}}

_DOCUMENT: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {
        "title": "psi-agent Event Daemon API",
        "version": "1.0.0",
        "description": (
            "Provider-neutral CloudEvent ingress and lease-based durable delivery. "
            "Bearer authentication is required when the daemon is configured with an API token."
        ),
    },
    "paths": {
        "/openapi.json": {
            "get": {
                "summary": "OpenAPI 3.1 contract",
                "responses": {
                    "200": {
                        "description": "The Event Daemon HTTP contract",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                            }
                        },
                    }
                },
            }
        },
        "/livez": {
            "get": {
                "summary": "Process liveness",
                "responses": {
                    "200": {
                        "description": "The process is running",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Health"},
                            }
                        },
                    }
                },
            }
        },
        "/readyz": {
            "get": {
                "summary": "Storage readiness",
                "responses": {
                    "200": {
                        "description": "The durable store is ready",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Health"},
                            }
                        },
                    },
                    "503": {
                        "description": "The durable store is not ready",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Health"},
                            }
                        },
                    },
                },
            }
        },
        "/health": {
            "get": {
                "summary": "Delivery health and backlog",
                "responses": {
                    "200": {
                        "description": "Current delivery counters",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["ok", "deliveries"],
                                    "properties": {
                                        "ok": {"type": "boolean"},
                                        "deliveries": {
                                            "type": "object",
                                            "additionalProperties": {"type": "integer"},
                                        },
                                    },
                                    "additionalProperties": False,
                                }
                            }
                        },
                    }
                },
            }
        },
        "/v1/events": {
            "post": {
                "summary": "Persist one strict five-field CloudEvent",
                "description": (
                    "A 202 response means the inbox transaction committed. "
                    "matchedSubscriptions can be zero; publishers that require downstream "
                    "processing should treat zero as a configuration error."
                ),
                "security": [{}, {"bearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CloudEvent"},
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "The event was durably accepted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EventAcceptance"},
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "503": {"$ref": "#/components/responses/Unavailable"},
                },
            }
        },
        "/hooks/{hook_id}/{token}": {
            "post": {
                "summary": "Wrap arbitrary JSON in a configured CloudEvent",
                "security": [],
                "parameters": [
                    {
                        "name": "hook_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "token",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "password"},
                    },
                ],
                "requestBody": {
                    "required": True,
                    "content": deepcopy(_JSON),
                },
                "responses": {
                    "202": {
                        "description": "The wrapped event was durably accepted",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EventAcceptance"},
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "503": {"$ref": "#/components/responses/Unavailable"},
                },
            }
        },
        "/internal/v1/subscriptions/{subscription_id}": {
            "get": {
                "summary": "Inspect one configured subscription",
                "description": "Adapters use this endpoint at startup to reject filter or ID mismatches.",
                "security": [{}, {"bearerAuth": []}],
                "parameters": [{"$ref": "#/components/parameters/SubscriptionId"}],
                "responses": {
                    "200": {
                        "description": "The configured subscription",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Subscription"},
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/internal/v1/subscriptions/{subscription_id}/claim": {
            "post": {
                "summary": "Claim ready deliveries under a lease",
                "security": [{}, {"bearerAuth": []}],
                "parameters": [{"$ref": "#/components/parameters/SubscriptionId"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ClaimRequest"},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Zero or more claimed deliveries",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ClaimResponse"},
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/internal/v1/deliveries/{delivery_id}/{action}": {
            "post": {
                "summary": "Renew, ACK, or NACK one active delivery lease",
                "description": (
                    "renew accepts leaseSeconds (default 60); nack accepts error and retrySeconds; "
                    "ack only requires leaseToken."
                ),
                "security": [{}, {"bearerAuth": []}],
                "parameters": [
                    {
                        "name": "delivery_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "action",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "enum": ["renew", "ack", "nack"]},
                    },
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/LeaseControl"},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "The lease operation completed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["ok", "result"],
                                    "properties": {
                                        "ok": {"const": True},
                                        "result": {},
                                    },
                                    "additionalProperties": False,
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        },
        "parameters": {
            "SubscriptionId": {
                "name": "subscription_id",
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
        },
        "schemas": {
            "Health": {
                "type": "object",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
                "additionalProperties": False,
            },
            "CloudEvent": {
                "type": "object",
                "description": "CloudEvents 1.0 using the Event Daemon strict five-field profile.",
                "required": ["specversion", "id", "source", "type", "data"],
                "properties": {
                    "specversion": {"const": "1.0"},
                    "id": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "minLength": 1},
                    "type": {"type": "string", "minLength": 1},
                    "data": {},
                },
                "additionalProperties": False,
            },
            "EventAcceptance": {
                "type": "object",
                "required": ["status", "eventSeq", "matchedSubscriptions"],
                "properties": {
                    "status": {"type": "string", "enum": ["created", "duplicate"]},
                    "eventSeq": {"type": "integer", "minimum": 1},
                    "matchedSubscriptions": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            "Subscription": {
                "type": "object",
                "required": ["id", "filter", "leaseSeconds", "maxAttempts"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "filter": {
                        "type": "object",
                        "required": ["sourcePrefix", "types"],
                        "properties": {
                            "sourcePrefix": {"type": "string"},
                            "types": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                        },
                        "additionalProperties": False,
                    },
                    "leaseSeconds": {"type": "integer", "minimum": 1},
                    "maxAttempts": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
            "ClaimRequest": {
                "type": "object",
                "required": ["instanceId"],
                "properties": {
                    "instanceId": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 1},
                    "leaseSeconds": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                        "description": "Zero or omitted uses the subscription default.",
                    },
                    "waitSeconds": {"type": "integer", "minimum": 0, "maximum": 30, "default": 0},
                },
            },
            "Delivery": {
                "type": "object",
                "required": ["deliveryId", "leaseToken", "leaseUntil", "attempt", "event"],
                "properties": {
                    "deliveryId": {"type": "string"},
                    "leaseToken": {"type": "string"},
                    "leaseUntil": {"type": "integer"},
                    "attempt": {"type": "integer", "minimum": 1},
                    "event": {"$ref": "#/components/schemas/CloudEvent"},
                },
                "additionalProperties": False,
            },
            "ClaimResponse": {
                "type": "object",
                "required": ["deliveries"],
                "properties": {
                    "deliveries": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Delivery"},
                    }
                },
                "additionalProperties": False,
            },
            "LeaseControl": {
                "type": "object",
                "required": ["leaseToken"],
                "properties": {
                    "leaseToken": {"type": "string", "minLength": 1},
                    "leaseSeconds": {"type": "integer", "minimum": 1},
                    "error": {"type": "string"},
                    "retrySeconds": {"type": "integer", "minimum": 0},
                },
            },
            "Error": {
                "type": "object",
                "required": ["error"],
                "properties": {"error": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        "responses": {
            "BadRequest": {
                "description": "Invalid request",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    }
                },
            },
            "Unauthorized": {
                "description": "Bearer token missing or invalid",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    }
                },
            },
            "NotFound": {
                "description": "The requested resource does not exist",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    }
                },
            },
            "Conflict": {
                "description": "Conflicting CloudEvent content or stale lease",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    }
                },
            },
            "Unavailable": {
                "description": "Durable storage is unavailable",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                    }
                },
            },
        },
    },
}


def eventd_openapi() -> dict[str, Any]:
    """Return a caller-owned OpenAPI document."""
    return deepcopy(_DOCUMENT)
