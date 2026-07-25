from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import assert_never


class CredentialSource(StrEnum):
    ENVIRONMENT = "environment"
    KEYRING = "keyring"
    LEGACY_FILE = "legacy_file"


@dataclass(frozen=True, slots=True)
class KeyringReadFailureWarning:
    pass


@dataclass(frozen=True, slots=True)
class LegacyMigrationFailureWarning:
    pass


@dataclass(frozen=True, slots=True)
class StaleLegacyCredentialWarning:
    guidance: str = "Remove the legacy credential file manually after verifying keyring access."


type CredentialWarning = (
    KeyringReadFailureWarning | LegacyMigrationFailureWarning | StaleLegacyCredentialWarning
)


@dataclass(frozen=True, slots=True)
class LegacyMigrationNotAttempted:
    pass


@dataclass(frozen=True, slots=True)
class LegacyMigrationSucceeded:
    pass


@dataclass(frozen=True, slots=True)
class LegacyMigrationFailed:
    pass


type LegacyMigrationOutcome = (
    LegacyMigrationNotAttempted | LegacyMigrationSucceeded | LegacyMigrationFailed
)


@dataclass(frozen=True, slots=True)
class EnvironmentCredential:
    api_key: str
    source: CredentialSource = field(default=CredentialSource.ENVIRONMENT, init=False)


@dataclass(frozen=True, slots=True)
class KeyringCredential:
    api_key: str
    warnings: tuple[CredentialWarning, ...] = ()
    source: CredentialSource = field(default=CredentialSource.KEYRING, init=False)


@dataclass(frozen=True, slots=True)
class LegacyCredential:
    api_key: str
    migration: LegacyMigrationOutcome
    warnings: tuple[CredentialWarning, ...] = ()
    source: CredentialSource = field(default=CredentialSource.LEGACY_FILE, init=False)


@dataclass(frozen=True, slots=True)
class MissingCredential:
    warnings: tuple[CredentialWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class EmptyLegacyCredential:
    warnings: tuple[CredentialWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class CorruptLegacyCredential:
    warnings: tuple[CredentialWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class UnreadableLegacyCredential:
    warnings: tuple[CredentialWarning, ...] = ()


type CredentialReadOutcome = (
    EnvironmentCredential
    | KeyringCredential
    | LegacyCredential
    | MissingCredential
    | EmptyLegacyCredential
    | CorruptLegacyCredential
    | UnreadableLegacyCredential
)


def credential_value(outcome: CredentialReadOutcome) -> str | None:
    match outcome:
        case (
            EnvironmentCredential(api_key=api_key)
            | KeyringCredential(api_key=api_key)
            | LegacyCredential(api_key=api_key)
        ):
            return api_key
        case (
            MissingCredential()
            | EmptyLegacyCredential()
            | CorruptLegacyCredential()
            | UnreadableLegacyCredential()
        ):
            return None
        case unreachable:
            assert_never(unreachable)


def stale_legacy_credential_guidance(outcome: CredentialReadOutcome) -> str | None:
    match outcome:
        case EnvironmentCredential():
            return None
        case (
            KeyringCredential(warnings=warnings)
            | LegacyCredential(warnings=warnings)
            | MissingCredential(warnings=warnings)
            | EmptyLegacyCredential(warnings=warnings)
            | CorruptLegacyCredential(warnings=warnings)
            | UnreadableLegacyCredential(warnings=warnings)
        ):
            for warning in warnings:
                match warning:
                    case StaleLegacyCredentialWarning(guidance=guidance):
                        return guidance
                    case KeyringReadFailureWarning() | LegacyMigrationFailureWarning():
                        continue
            return None
        case unreachable:
            assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class KeyringCredentialSaved:
    pass


@dataclass(frozen=True, slots=True)
class KeyringCredentialSaveFailed:
    pass


@dataclass(frozen=True, slots=True)
class KeyringCredentialUnavailable:
    pass


@dataclass(frozen=True, slots=True)
class EmptyCredentialRejected:
    pass


type CredentialSaveOutcome = (
    KeyringCredentialSaved
    | KeyringCredentialSaveFailed
    | KeyringCredentialUnavailable
    | EmptyCredentialRejected
)
