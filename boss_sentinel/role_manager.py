"""Role Manager for Boss Sentinel.

Maps recognized person names to identity roles (owner, boss, colleague, unknown).
Roles are configured via the ``roles`` field in config.json and determine how
each feature module behaves for different people.

Role hierarchy:
    - owner:     The computer user (drives pomodoro, attention tracking)
    - boss:      Target persons who trigger defensive actions (lock, alert)
    - colleague: Known persons who are neither owner nor boss
    - unknown:   Any face not matching a known person (default for unrecognized)
"""

import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Valid role names
VALID_ROLES = {"owner", "boss", "colleague"}


class RoleManager:
    """Resolve person identities to roles.

    The manager builds a reverse lookup table (person_name -> role) from the
    roles configuration dict.  Lookup is O(1) and case-insensitive.

    Example::

        rm = RoleManager({"owner": ["alice"], "boss": ["bob"]})
        rm.resolve("alice")     # "owner"
        rm.resolve("bob")       # "boss"
        rm.resolve("charlie")   # "colleague" (known but unassigned)
        rm.resolve(None)        # "unknown"
    """

    def __init__(self, roles_config: Optional[Dict[str, List[str]]] = None) -> None:
        self._name_to_role: Dict[str, str] = {}
        self._roles_config: Dict[str, List[str]] = {}
        self.update_roles(roles_config or {})

    def update_roles(self, roles_config: Dict[str, List[str]]) -> None:
        """Rebuild the lookup table from a new roles config.

        Args:
            roles_config: Maps role name to list of person names,
                e.g. ``{"owner": ["alice"], "boss": ["bob"]}``.
        """
        self._roles_config = {}
        self._name_to_role.clear()

        for role, names in roles_config.items():
            role_lower = role.lower()
            if role_lower not in VALID_ROLES:
                logger.warning("Unknown role '%s' ignored (valid: %s)", role, VALID_ROLES)
                continue
            self._roles_config[role_lower] = list(names)
            for name in names:
                name_lower = name.lower()
                if name_lower in self._name_to_role:
                    old_role = self._name_to_role[name_lower]
                    logger.warning(
                        "Person '%s' assigned to both '%s' and '%s'; using '%s'",
                        name, old_role, role_lower, role_lower,
                    )
                self._name_to_role[name_lower] = role_lower

        total = len(self._name_to_role)
        if total:
            logger.info("RoleManager: %d person(s) mapped to roles", total)
        else:
            logger.info("RoleManager: no role mappings configured (legacy mode)")

    def resolve(self, person_name: Optional[str]) -> str:
        """Resolve a person name to a role.

        Args:
            person_name: Recognized person name, or ``None`` / empty for
                unrecognized faces.

        Returns:
            One of ``"owner"``, ``"boss"``, ``"colleague"``, or ``"unknown"``.
        """
        if not person_name:
            return "unknown"

        name_lower = person_name.lower()
        role = self._name_to_role.get(name_lower)
        if role:
            return role

        # Known face not assigned to any role -> default to colleague
        return "colleague"

    # --- Convenience predicates ---

    def is_owner(self, person_name: Optional[str]) -> bool:
        return self.resolve(person_name) == "owner"

    def is_boss(self, person_name: Optional[str]) -> bool:
        return self.resolve(person_name) == "boss"

    def is_unknown(self, person_name: Optional[str]) -> bool:
        return self.resolve(person_name) == "unknown"

    def is_colleague(self, person_name: Optional[str]) -> bool:
        return self.resolve(person_name) == "colleague"

    # --- Query helpers ---

    def get_role_members(self, role: str) -> List[str]:
        """Return all person names assigned to a given role."""
        return self._roles_config.get(role.lower(), [])

    def get_owner_names(self) -> List[str]:
        """Return the list of owner names."""
        return self.get_role_members("owner")

    def get_boss_names(self) -> List[str]:
        """Return the list of boss names."""
        return self.get_role_members("boss")

    def get_all_roles(self) -> Dict[str, List[str]]:
        """Return the full roles config dict."""
        return dict(self._roles_config)
