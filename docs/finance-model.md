# Modelo financiero — Brújula

Este documento define **cómo se calcula el dinero**. Es la especificación que implementa
`domain/`. Todos los parámetros son configurables vía `.env` (no hardcodear).

---

## 1. Ingreso neto (Ecuador)

```
neto_sueldo   = BASE_SALARY * (1 - IESS_PERSONAL_RATE) - INCOME_TAX_MONTHLY
ingreso_total = neto_sueldo + ingresos_extra_del_mes
```

Con los valores actuales:

```
1600 * (1 - 0.0945) = 1448.80      # aporte IESS 9.45%
- 0 (impuesto a la renta)          # ajustable si aplica
= 1448.80  neto del sueldo
+ ~100     proyectos externos (promedio)
≈ 1548.80  ingreso disponible mensual
```

> El aporte personal al IESS para afiliados en relación de dependencia es **9,45 %**.
> El impuesto a la renta se deja en 0 por defecto (con deducción de gastos personales
> suele anularse a este nivel de ingreso); es un parámetro ajustable.

**Fuentes de ingreso** (las distingue el agente): `trabajo` · `proyecto_personal`.

---

## 2. Presupuesto por sobres ("buckets") con arrastre

Cada mes, parte del ingreso se **asigna** a sobres. Lo no gastado **NO se pierde**: se
acumula (rollover) y queda disponible.

| Sobre | Asignación | Tipo |
|---|---|---|
| Iglesia | `IGLESIA_FIJO` ($60) | gasto/aporte fijo |
| Familia | `PCT_FAMILIA` (10 %) del ingreso | reserva con arrastre |
| Relación (pareja) | `PCT_RELACION` (10 %) del ingreso | reserva con arrastre |
| Vida / gastos hormiga | resto operativo | gasto |
| Ahorro metas | excedente | hacia metas |

**Semáforo mensual por sobre:**
- 🟢 **Verde**: gastaste ≤ lo asignado (ahorraste, el sobrante se arrastra).
- 🟡 **Amarillo**: cerca del límite (configurable, p.ej. 80–100 %).
- 🔴 **Rojo**: te pasaste de lo asignado.

```
saldo_sobre(mes) = saldo_sobre(mes-1) + asignacion(mes) - gastado(mes)
```

---

## 3. Metas (ahorro a contado)

Ambas metas se pagan **a contado** (es ahorro acumulado, no crédito). La fecha objetivo
se **deriva de la edad**: `fecha_objetivo = BIRTH_DATE + edad`.

| Meta | Monto | Objetivo por edad | Fecha (derivada) |
|---|---|---|---|
| 🚗 Carro eléctrico | `META_CARRO` = $27.000 | `META_CARRO_EDAD` = antes de los 30 | `BIRTH_DATE + 30` |
| 🏠 Casa | `META_CASA` = $100.000 | `META_CASA_EDAD` = antes de los 35 | `BIRTH_DATE + 35` |

Para cada meta el sistema calcula:

```
restante           = monto - ahorrado
meses_objetivo     = meses entre hoy y fecha_objetivo
ahorro_necesario   = restante / meses_objetivo          # para llegar a tiempo
ahorro_actual      = promedio de aporte mensual reciente
fecha_proyectada   = hoy + (restante / ahorro_actual) meses
brecha             = ahorro_necesario - ahorro_actual    # cuánto falta por mes
```

### Realidad actual (transparencia)

Con el nuevo horizonte (carro a los 30, casa a los 35) las metas son más alcanzables que
antes, pero aún exigen subir ingresos:

- 🚗 Carro $27.000 a ~2-3 años ≈ **$900–1.250/mes**.
- 🏠 Casa $100.000 a ~7 años ≈ **$1.100–1.200/mes**.

Al ritmo de ahorro actual (~$600–700/mes) todavía hay brecha. El dashboard muestra ambas
fechas (objetivo vs **proyectada**) y el **ingreso adicional requerido**. Es intencional:
el sistema mide y motiva el crecimiento de ingresos.

### Sección motivadora ("¿a qué edad lo logro?")

Bloque destacado del dashboard y de los reportes por Telegram. Convierte la fecha
proyectada en **edad** y en cuenta regresiva, con el mensaje que pediste:

```
fecha_proyectada = hoy + (restante / ahorro_actual) meses
edad_al_lograrlo = años/meses entre BIRTH_DATE y fecha_proyectada
faltan           = años/meses entre hoy y fecha_proyectada
```

> *"Al paso de ahorro e ingresos que llevas, conseguirás el carro a los 31 años y 4 meses
> (te faltan 3 años 2 meses). Para lograrlo antes de los 30 necesitas +$420/mes."*

Si vas adelantado respecto a la meta → mensaje en 🟢; si vas atrasado → 🟡/🔴 con el
empujón concreto (cuánto más ahorrar o ingresar).

---

## 4. Simulador "¿y si subo mis ingresos?"

Función estrella del dashboard. Dado un aumento `Δ` de ingreso mensual destinado a una
meta:

```
nueva_fecha   = hoy + (restante / (ahorro_actual + Δ)) meses
meses_ahorrados = fecha_proyectada_actual - nueva_fecha
```

Mensaje tipo: *"Si subes tus ingresos $300/mes hacia el carro, lo tendrías ~9 meses
antes."* Esto convierte la app en un juego: cada dólar extra mueve la aguja.

---

## 5. Indicadores de progreso

- Ingreso mensual y **su crecimiento** (mes a mes, promedio anual).
- % de avance por meta.
- Semáforo por sobre y del mes global.
- Tasa de ahorro (ahorro / ingreso).
- "Racha" de meses en verde (gamificación).

---

## 6. Esquema de datos (implementado en `db/models.py`)

> **Todo vive en la base de datos, NADA en `.env`.** Al iniciar, `db/seed.py` siembra los
> parámetros, metas y sobres por defecto (idempotente). Se editan/consultan por Telegram
> o el dashboard.

```
parameters   (key, value, description)   # birth_date, base_salary, iess_personal_rate,
                                          # income_tax_monthly, extra_income_baseline,
                                          # saldo_inicial, timezone, currency
goals        (id, nombre, monto_objetivo, edad_objetivo, ahorrado)   # carro, casa
envelopes    (id, nombre, tipo[fijo|porcentaje], valor, arrastre)    # familia, relacion, iglesia
incomes      (id, fecha, monto, fuente[trabajo|proyecto_personal], descripcion, creado_en)
expenses     (id, fecha, monto, categoria, sobre, descripcion, creado_en)
```

Categorías de gasto iniciales (configurables): `pareja`, `familia`, `iglesia`,
`personal`, `salud` (minoxidil, etc.), `comida`, `transporte`, `otros`.
