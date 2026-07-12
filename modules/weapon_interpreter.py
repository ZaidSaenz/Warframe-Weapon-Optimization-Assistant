# modules/weapon_interpreter.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


INTERPRETATION_VERSION = 1
SUPPORTED_WEAPON_SCHEMA = 3

RATING_LABELS = {
    "very_low": "muy bajo",
    "low": "bajo",
    "moderate": "moderado",
    "high": "alto",
    "very_high": "muy alto",
}

DAMAGE_LABELS = {
    "impact": "Impacto",
    "puncture": "Perforación",
    "slash": "Corte",
    "heat": "Calor",
    "cold": "Frío",
    "electricity": "Electricidad",
    "toxin": "Toxina",
    "blast": "Explosión",
    "corrosive": "Corrosivo",
    "gas": "Gas",
    "magnetic": "Magnético",
    "radiation": "Radiación",
    "viral": "Viral",
    "void": "Vacío",
}


class WeaponInterpretationError(ValueError):
    pass


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WeaponInterpretationError(
            f"La sección {field} no contiene un Mapping válido."
        )
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise WeaponInterpretationError(f"{field} debe ser numérico.")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise WeaponInterpretationError(
            f"{field} debe ser numérico."
        ) from error


def _round(value: float, decimals: int = 4) -> float:
    return round(float(value), decimals)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _piecewise_score(
    value: float,
    points: Sequence[tuple[float, float]],
) -> float:
    if not points:
        return 0.0

    ordered = sorted(points, key=lambda item: item[0])

    if value <= ordered[0][0]:
        return _clamp(ordered[0][1])

    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if value <= x1:
            if x1 == x0:
                return _clamp(y1)
            ratio = (value - x0) / (x1 - x0)
            return _clamp(y0 + ratio * (y1 - y0))

    return _clamp(ordered[-1][1])


def _rating(score: float) -> str:
    if score < 0.20:
        return "very_low"
    if score < 0.40:
        return "low"
    if score < 0.62:
        return "moderate"
    if score < 0.82:
        return "high"
    return "very_high"


def _finding(
    code: str,
    statement: str,
    evidence: Sequence[str],
    *,
    importance: str = "medium",
) -> dict[str, Any]:
    return {
        "code": code,
        "statement": statement,
        "evidence": list(evidence),
        "importance": importance,
    }


def _damage_profile(damage: Mapping[str, Any]) -> dict[str, Any]:
    dominant_type = damage.get("dominant_type")
    dominant_percent = _number(
        damage.get("dominant_percent", 0.0),
        "damage.dominant_percent",
    )

    if dominant_percent >= 65.0:
        concentration = "strongly_concentrated"
        concentration_label = "muy concentrada"
    elif dominant_percent >= 45.0:
        concentration = "concentrated"
        concentration_label = "concentrada"
    else:
        concentration = "mixed"
        concentration_label = "repartida"

    dominant_label = (
        DAMAGE_LABELS.get(str(dominant_type), str(dominant_type))
        if dominant_type
        else "sin tipo dominante"
    )

    return {
        "dominant_type": dominant_type,
        "dominant_label": dominant_label,
        "dominant_percent": _round(dominant_percent),
        "concentration": concentration,
        "concentration_label": concentration_label,
        "physical_percent": _round(
            _number(damage.get("physical_percent", 0.0), "physical_percent")
        ),
        "elemental_percent": _round(
            _number(damage.get("elemental_percent", 0.0), "elemental_percent")
        ),
        "evidence": (
            f"{dominant_label} representa {dominant_percent:.1f} % del daño base; "
            f"la distribución es {concentration_label}."
        ),
    }


def _critical_profile(
    core_stats: Mapping[str, Any],
    derived: Mapping[str, Any],
    *,
    category: str,
) -> dict[str, Any]:
    chance = _number(
        core_stats.get("critical_chance_percent"),
        "critical_chance_percent",
    )
    multiplier = _number(
        core_stats.get("critical_multiplier"),
        "critical_multiplier",
    )
    expected_factor = _number(
        derived.get("expected_critical_damage_factor"),
        "expected_critical_damage_factor",
    )

    chance_score = _piecewise_score(
        chance,
        (
            (0.0, 0.0),
            (10.0, 0.15),
            (20.0, 0.42),
            (30.0, 0.68),
            (40.0, 0.84),
            (60.0, 1.0),
        ),
    )
    multiplier_score = _piecewise_score(
        multiplier,
        (
            (1.0, 0.0),
            (1.5, 0.15),
            (2.0, 0.45),
            (2.5, 0.68),
            (3.0, 0.84),
            (4.0, 1.0),
        ),
    )

    score = 0.56 * chance_score + 0.44 * multiplier_score

    if chance < 10.0:
        score = min(score, 0.35)
    if multiplier < 1.5:
        score = min(score, 0.35)

    reliability = chance
    reliability_source = "probabilidad crítica por impacto"

    if category in {"primary", "secondary"}:
        reliability = _number(
            derived.get(
                "chance_at_least_one_critical_hit_per_shot_percent",
                chance,
            ),
            "chance_at_least_one_critical_hit_per_shot_percent",
        )
        reliability_source = "probabilidad de al menos un crítico por disparo"

    return {
        "score": _round(score),
        "rating": _rating(score),
        "rating_label": RATING_LABELS[_rating(score)],
        "chance_percent": _round(chance),
        "multiplier": _round(multiplier),
        "expected_damage_factor": _round(expected_factor),
        "reliability_percent": _round(reliability),
        "evidence": [
            (
                f"{chance:.1f} % de probabilidad crítica junto con "
                f"{multiplier:.2f}x de multiplicador."
            ),
            (
                f"El factor crítico promedio calculado es "
                f"{expected_factor:.2f}x."
            ),
            (
                f"La {reliability_source} es aproximadamente "
                f"{reliability:.1f} %."
            ),
        ],
    }


def _status_profile(
    core_stats: Mapping[str, Any],
    derived: Mapping[str, Any],
    *,
    category: str,
) -> dict[str, Any]:
    chance = _number(
        core_stats.get("status_chance_percent"),
        "status_chance_percent",
    )

    per_hit_score = _piecewise_score(
        chance,
        (
            (0.0, 0.0),
            (10.0, 0.20),
            (20.0, 0.45),
            (30.0, 0.65),
            (50.0, 0.85),
            (100.0, 1.0),
        ),
    )

    evidence = [f"La probabilidad de estado por impacto es {chance:.1f} %."]
    throughput = None
    reliability = chance
    score = per_hit_score
    throughput_rating = None

    if category in {"primary", "secondary"}:
        throughput = _number(
            derived.get("expected_status_procs_per_second"),
            "expected_status_procs_per_second",
        )
        reliability = _number(
            derived.get(
                "chance_at_least_one_status_proc_per_shot_percent",
                chance,
            ),
            "chance_at_least_one_status_proc_per_shot_percent",
        )
        throughput_score = _piecewise_score(
            throughput,
            (
                (0.0, 0.0),
                (0.5, 0.22),
                (1.0, 0.42),
                (2.0, 0.64),
                (4.0, 0.82),
                (8.0, 1.0),
            ),
        )
        score = 0.56 * per_hit_score + 0.44 * throughput_score
        throughput_rating = _rating(throughput_score)
        evidence.extend([
            (
                f"La frecuencia nominal produce cerca de "
                f"{throughput:.2f} procs esperados por segundo."
            ),
            (
                f"La probabilidad de al menos un proc por disparo es "
                f"aproximadamente {reliability:.1f} %."
            ),
        ])
    else:
        evidence.append(
            "No se transforma attack_speed en procs por segundo porque faltan postura y animaciones."
        )

    return {
        "score": _round(score),
        "rating": _rating(score),
        "rating_label": RATING_LABELS[_rating(score)],
        "chance_percent": _round(chance),
        "reliability_percent": _round(reliability),
        "expected_procs_per_second": (
            _round(throughput) if throughput is not None else None
        ),
        "throughput_rating": throughput_rating,
        "evidence": evidence,
    }


def _impact_frequency_profile(
    derived: Mapping[str, Any],
) -> dict[str, Any] | None:
    value = derived.get("nominal_instances_per_second")
    if value is None:
        return None

    instances = _number(value, "nominal_instances_per_second")

    if instances < 3.0:
        rating = "low"
        label = "baja"
    elif instances < 8.0:
        rating = "moderate"
        label = "moderada"
    elif instances < 20.0:
        rating = "high"
        label = "alta"
    else:
        rating = "very_high"
        label = "muy alta"

    return {
        "instances_per_second": _round(instances),
        "rating": rating,
        "rating_label": label,
        "evidence": (
            f"La estimación nominal es de {instances:.2f} instancias de impacto por segundo."
        ),
    }


def _continuity_profile(
    classification: Mapping[str, Any],
    derived: Mapping[str, Any],
) -> dict[str, Any]:
    magazine_duration = _number(
        derived.get("magazine_duration_seconds"),
        "magazine_duration_seconds",
    )
    reload_type = str(classification.get("reload_type", "magazine"))

    if magazine_duration < 2.0:
        window = "very_short"
        window_label = "muy corta"
    elif magazine_duration < 5.0:
        window = "short"
        window_label = "corta"
    elif magazine_duration < 10.0:
        window = "medium"
        window_label = "media"
    elif magazine_duration < 20.0:
        window = "long"
        window_label = "larga"
    else:
        window = "very_long"
        window_label = "muy larga"

    downtime = None
    for key in (
        "reload_downtime_percent",
        "full_recharge_downtime_percent",
        "full_reload_downtime_percent",
    ):
        if derived.get(key) is not None:
            downtime = _number(derived.get(key), key)
            break

    if downtime is None:
        pressure = "unknown"
        pressure_label = "no determinada"
    elif downtime < 15.0:
        pressure = "low"
        pressure_label = "baja"
    elif downtime < 30.0:
        pressure = "moderate"
        pressure_label = "moderada"
    elif downtime < 45.0:
        pressure = "high"
        pressure_label = "alta"
    else:
        pressure = "very_high"
        pressure_label = "muy alta"

    evidence = [
        f"El cargador sostiene aproximadamente {magazine_duration:.2f} s de uso continuo."
    ]
    if downtime is not None:
        evidence.append(
            f"La recuperación completa ocupa cerca de {downtime:.1f} % del ciclo estimado."
        )

    return {
        "reload_type": reload_type,
        "magazine_duration_seconds": _round(magazine_duration),
        "fire_window": window,
        "fire_window_label": window_label,
        "downtime_percent": _round(downtime) if downtime is not None else None,
        "reload_pressure": pressure,
        "reload_pressure_label": pressure_label,
        "evidence": evidence,
    }


def _select_tendency(
    critical: Mapping[str, Any],
    status: Mapping[str, Any],
) -> tuple[str, str]:
    critical_score = _number(critical.get("score"), "critical.score")
    status_score = _number(status.get("score"), "status.score")

    if critical_score >= 0.62 and status_score >= 0.62:
        return (
            "hybrid",
            "Perfil híbrido: crítico y estado muestran soporte estadístico suficiente.",
        )

    if critical_score >= 0.50 and critical_score - status_score >= 0.10:
        return (
            "critical",
            "Tendencia crítica: la combinación de probabilidad y multiplicador supera al perfil de estado.",
        )

    if status_score >= 0.50 and status_score - critical_score >= 0.10:
        return (
            "status",
            "Tendencia de estado: la probabilidad y la frecuencia de aplicación superan al perfil crítico.",
        )

    if critical_score < 0.40 and status_score < 0.40:
        return (
            "no_clear_specialization",
            "Sin especialización clara en crítico o estado con los datos disponibles.",
        )

    return (
        "balanced",
        "Perfil equilibrado sin una ventaja suficientemente amplia para declarar una tendencia única.",
    )


def _confidence_profile(
    weapon_data: Mapping[str, Any],
    *,
    category: str,
    classification: Mapping[str, Any] | None,
    melee_stats: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = weapon_data.get("context") or {}
    if not isinstance(context, Mapping):
        context = {}

    score = 0.78
    limits: list[str] = [
        "No se conocen pasivas, evoluciones, disparos alternativos ni interacciones externas no declaradas."
    ]
    missing_context: list[str] = [
        "economía total de munición",
        "precisión y retroceso",
        "caída de daño y comportamiento contra objetivos reales",
    ]

    if category in {"primary", "secondary"} and classification is not None:
        firing_mode = classification.get("firing_mode")
        delivery = classification.get("damage_delivery")
        reload_type = classification.get("reload_type")

        if firing_mode in {"burst", "charge", "continuous"}:
            score -= 0.10
            limits.append(
                "El modo de disparo requiere aproximaciones porque no se modelan todas sus pausas o animaciones."
            )

        if delivery == "projectile":
            score -= 0.05
            missing_context.append("facilidad real para acertar proyectiles")

        if reload_type in {"battery", "shell_by_shell"}:
            score -= 0.05
            limits.append(
                "La continuidad se calcula con un ciclo completo y no representa todos los patrones de recarga parcial."
            )

    if category == "melee":
        score -= 0.22
        limits.append(
            "La velocidad de ataque no equivale a ataques por segundo sin postura, animaciones e impactos por movimiento."
        )
        missing_context.extend([
            "postura",
            "multiplicadores de combo y golpes forzados",
            "geometría real de ataques ligeros y pesados",
        ])

        if melee_stats and not melee_stats.get("melee_family"):
            score -= 0.05
            missing_context.append("familia del arma melee")

    if context.get("has_special_mechanics"):
        score -= 0.12
        limits.append(
            "El arma declara mecánicas especiales que no están convertidas en reglas estructuradas."
        )

    score = _clamp(score)
    if score >= 0.80:
        level = "high"
        label = "alta"
    elif score >= 0.60:
        level = "medium"
        label = "media"
    else:
        level = "low"
        label = "baja"

    return {
        "score": _round(score),
        "level": level,
        "label": label,
        "scope": "solo estadísticas base y relaciones calculables",
        "limits": limits,
        "missing_context": list(dict.fromkeys(missing_context)),
    }


def interpret_weapon_data(weapon_data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(weapon_data, Mapping):
        raise TypeError("weapon_data debe ser un diccionario o Mapping.")

    if weapon_data.get("schema_version") != SUPPORTED_WEAPON_SCHEMA:
        raise WeaponInterpretationError(
            "El intérprete requiere datos del parser con schema_version 3."
        )

    category = str(weapon_data.get("weapon_category"))
    if category not in {"primary", "secondary", "melee"}:
        raise WeaponInterpretationError("La categoría del arma no es válida.")

    damage = _as_mapping(weapon_data.get("damage"), "damage")
    core_stats = _as_mapping(weapon_data.get("core_stats"), "core_stats")
    derived = _as_mapping(weapon_data.get("derived"), "derived")

    classification: Mapping[str, Any] | None = None
    ranged_stats: Mapping[str, Any] | None = None
    melee_stats: Mapping[str, Any] | None = None

    if category in {"primary", "secondary"}:
        classification = _as_mapping(
            weapon_data.get("ranged_classification"),
            "ranged_classification",
        )
        ranged_stats = _as_mapping(
            weapon_data.get("ranged_stats"),
            "ranged_stats",
        )
    else:
        melee_stats = _as_mapping(
            weapon_data.get("melee_stats"),
            "melee_stats",
        )

    damage_profile = _damage_profile(damage)
    critical_profile = _critical_profile(
        core_stats,
        derived,
        category=category,
    )
    status_profile = _status_profile(
        core_stats,
        derived,
        category=category,
    )
    tendency_code, tendency_statement = _select_tendency(
        critical_profile,
        status_profile,
    )

    strengths: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    reinforce: list[str] = []
    correct: list[str] = []
    avoid_forcing: list[str] = []
    recommended_use: list[str] = []
    poor_fit: list[str] = []

    critical_score = _number(critical_profile["score"], "critical.score")
    status_score = _number(status_profile["score"], "status.score")

    if critical_score >= 0.62:
        strengths.append(_finding(
            "critical_support",
            "El perfil crítico es una fortaleza estadística.",
            critical_profile["evidence"][:2],
            importance="high",
        ))
        reinforce.append(
            "Reforzar la ruta crítica porque probabilidad y multiplicador ya trabajan juntos."
        )
        recommended_use.append(
            "Uso que aproveche impactos repetidos o confiables para convertir con frecuencia el buen multiplicador crítico."
        )
    elif critical_score < 0.40:
        limitations.append(_finding(
            "weak_critical_support",
            "El perfil crítico tiene soporte limitado.",
            critical_profile["evidence"][:2],
        ))
        avoid_forcing.append(
            "No convertir el crítico en la única identidad del arma con estos valores base."
        )
        poor_fit.append(
            "Estilos que dependan casi por completo de críticos frecuentes y potentes."
        )

    if status_score >= 0.62:
        strengths.append(_finding(
            "status_support",
            "El perfil de estado es una fortaleza estadística.",
            status_profile["evidence"],
            importance="high",
        ))
        reinforce.append(
            "Reforzar la aplicación de estado porque la probabilidad y su frecuencia efectiva ya son favorables."
        )
        recommended_use.append(
            "Uso basado en impactos repetidos y aplicación constante de efectos de estado."
        )
    elif status_score < 0.40:
        status_throughput = status_profile.get("expected_procs_per_second")
        if status_throughput is not None and float(status_throughput) >= 1.0:
            status_statement = (
                "El estado por impacto es limitado, aunque la frecuencia de impactos permite aplicaciones ocasionales."
            )
        else:
            status_statement = "El perfil de estado tiene soporte limitado."

        limitations.append(_finding(
            "weak_status_support",
            status_statement,
            status_profile["evidence"],
        ))
        avoid_forcing.append(
            "No depender principalmente de estado si la frecuencia efectiva no compensa la probabilidad base."
        )
        poor_fit.append(
            "Estilos cuyo rendimiento dependa principalmente de aplicar estados con cada disparo o impacto."
        )

    impact_frequency = None
    continuity = None

    if category in {"primary", "secondary"}:
        assert classification is not None
        assert ranged_stats is not None
        impact_frequency = _impact_frequency_profile(derived)
        continuity = _continuity_profile(classification, derived)

        if impact_frequency and impact_frequency["rating"] in {"high", "very_high"}:
            strengths.append(_finding(
                "high_impact_frequency",
                "La frecuencia nominal de impactos es alta.",
                [impact_frequency["evidence"]],
            ))

        fire_window = continuity["fire_window"]
        reload_pressure = continuity["reload_pressure"]

        if fire_window in {"long", "very_long"} and reload_pressure in {
            "low",
            "moderate",
        }:
            strengths.append(_finding(
                "good_continuity",
                "La relación entre cargador, cadencia y recarga favorece la continuidad.",
                continuity["evidence"],
                importance="high",
            ))
            recommended_use.append("Fuego sostenido y ventanas largas de ataque.")

        if fire_window in {"very_short", "short"}:
            limitations.append(_finding(
                "short_fire_window",
                "El cargador se agota rápidamente respecto a la cadencia.",
                continuity["evidence"],
                importance="high",
            ))
            correct.append(
                "Corregir la duración útil del cargador o moderar el consumo de munición."
            )
            poor_fit.append(
                "Fuego continuo prolongado sin pausas, porque la ventana antes de recargar es corta."
            )

        if reload_pressure in {"high", "very_high"}:
            limitations.append(_finding(
                "high_reload_pressure",
                "La recuperación del cargador ocupa una parte grande del ciclo.",
                continuity["evidence"],
                importance="high",
            ))
            correct.append(
                "Reducir la presión de recarga para evitar interrupciones frecuentes."
            )

        firing_mode = classification.get("firing_mode")
        if firing_mode == "charge":
            recommended_use.append("Disparos deliberados que acepten el tiempo de carga.")
            poor_fit.append("Respuesta inmediata o cadencia reactiva constante.")
        elif firing_mode == "burst":
            recommended_use.append("Ráfagas controladas y ventanas cortas de exposición.")
        elif firing_mode == "semi_automatic":
            recommended_use.append("Disparos controlados en lugar de mantener fuego automático.")
        elif firing_mode == "continuous":
            recommended_use.append("Seguimiento continuo del objetivo durante la aplicación del haz.")

        if classification.get("damage_delivery") == "projectile":
            limitations.append(_finding(
                "projectile_handling_unknown",
                "El desempeño práctico depende de acertar proyectiles con tiempo de viaje.",
                ["La velocidad de proyectil no se compara contra una familia de armas equivalente."],
            ))

    else:
        assert melee_stats is not None
        if melee_stats.get("heavy_attack_damage") is not None:
            limitations.append(_finding(
                "heavy_attack_context_incomplete",
                "Los datos pesados permiten comparar daño y preparación, pero no confirmar una especialización pesada.",
                [
                    "Faltan postura, golpes forzados, alcance efectivo, geometría y mecánicas especiales del ataque pesado."
                ],
            ))

        recommended_use.append(
            "Ataques ligeros o generales acordes con el perfil crítico/estado observado, sin asumir la velocidad real de la postura."
        )
        poor_fit.append(
            "Declarar el arma adecuada o inadecuada para ataques pesados únicamente por daño y preparación."
        )

    if tendency_code == "hybrid":
        reinforce.append(
            "Mantener ambas rutas; ninguna debe presentarse como secundaria débil."
        )
    elif tendency_code == "critical" and status_score < 0.50:
        avoid_forcing.append(
            "No describir el arma como híbrida mientras el perfil de estado permanezca claramente por debajo del crítico."
        )
    elif tendency_code == "status" and critical_score < 0.50:
        avoid_forcing.append(
            "No describir el arma como híbrida mientras el perfil crítico permanezca claramente por debajo del estado."
        )
    elif tendency_code == "no_clear_specialization":
        reinforce.append(
            "Priorizar rendimiento base y manejo antes de forzar una identidad crítica o de estado."
        )

    if not correct:
        correct.append(
            "No aparece una corrección operativa dominante dentro de las estadísticas disponibles."
        )

    confidence = _confidence_profile(
        weapon_data,
        category=category,
        classification=classification,
        melee_stats=melee_stats,
    )

    forbidden_conclusions = [
        "DPS real exacto",
        "build completa",
        "mods, Arcanos, Rivens, polaridades o Formas concretas",
        "mecánicas o pasivas no incluidas en la entrada",
    ]

    if category == "melee":
        forbidden_conclusions.extend([
            "ataques reales por segundo",
            "rendimiento exacto de postura",
            "idoneidad definitiva para ataques pesados",
        ])

    context = weapon_data.get("context") or {}
    if isinstance(context, Mapping) and context.get("has_special_mechanics"):
        forbidden_conclusions.append(
            "ignorar las mecánicas especiales declaradas"
        )

    return {
        "interpretation_version": INTERPRETATION_VERSION,
        "source_schema_version": weapon_data.get("schema_version"),
        "weapon_category": category,
        "data_source": weapon_data.get("data_source"),
        "tendency": {
            "code": tendency_code,
            "statement": tendency_statement,
            "evidence": [
                f"Perfil crítico: {critical_profile['rating_label']} ({critical_score:.2f}).",
                f"Perfil de estado: {status_profile['rating_label']} ({status_score:.2f}).",
            ],
        },
        "profiles": {
            "critical": critical_profile,
            "status": status_profile,
            "damage": damage_profile,
            "impact_frequency": impact_frequency,
            "continuity": continuity,
        },
        "strengths": strengths,
        "limitations": limitations,
        "priorities": {
            "reinforce": list(dict.fromkeys(reinforce)),
            "correct": list(dict.fromkeys(correct)),
            "avoid_forcing": list(dict.fromkeys(avoid_forcing)),
        },
        "use_cases": {
            "recommended": list(dict.fromkeys(recommended_use)),
            "poor_fit": list(dict.fromkeys(poor_fit)),
        },
        "confidence": confidence,
        "forbidden_conclusions": list(dict.fromkeys(forbidden_conclusions)),
        "calculation_assumptions": list(
            weapon_data.get("calculation_assumptions") or []
        ),
        "special_context": dict(context) if isinstance(context, Mapping) else {},
    }


interpret = interpret_weapon_data
