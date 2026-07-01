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

## 2. Presupuesto por sobres ("buckets")

Los % se calculan sobre el **ingreso TOTAL del mes** (sueldo neto + extra), así escalan
cuando suben los ingresos. Los sobres son **topes/metas**, no bolsillos con dinero
encerrado (ver modelo de ahorro abajo).

| Sobre | Asignación | Tipo |
|---|---|---|
| Familia | 10 % | porcentaje |
| Pareja | 10 % | porcentaje |
| Personal | 5 % (gym, café, salud, autocuidado) | porcentaje |
| Iglesia | $60 | fijo |
| Transporte | $60 | fijo |
| Ahorro | el resto | residual → metas |

> `ahorro` es además el **catch-all**: gastos sin un sobre específico (cursos/inversión,
> suscripciones como Shopify) salen del ahorro.

**Modelo de ahorro (confirmado):** `ahorro_del_mes = ingreso − gastos reales`. Gastar
menos que un tope = ahorraste esa diferencia → acelera las metas. El **semáforo** se
evalúa de forma **acumulada** por sobre, para que lo ahorrado antes cubra un gasto grande
después (efecto arrastre sin congelar plata lejos de las metas):

```
balance_sobre(hasta_mes) = Σ asignacion - Σ gastado
🟢 balance ≥ 0 (vas bien) · 🟡 cerca del tope · 🔴 te pasaste
```

**Pago:** siempre con tarjeta (no se registra método de pago).

---

## 3. Metas en **cascada por prioridad** (ahorro a contado)

Las metas se pagan **a contado** y se financian **en cascada por prioridad**: todo el
ahorro se acumula en la meta #1 hasta completarla; al comprarla, **empieza la #2 desde
cero**, y así sucesivamente. Esa es la única forma de saber *en qué orden y en qué fecha*
se logra cada una. Las metas son **editables** (crear/editar/eliminar/reordenar) desde la
pestaña **Metas** del dashboard; no viven en `.env`, viven en la tabla `goals`.

**Patrimonio (pool):** el reparto parte del ahorro acumulado real:

```
profit_total = Σ ingresos − Σ gastos   (todos los movimientos, histórico)
pool         = saldo_inicial + profit_total
```

**Reparto en cascada** (`domain/goals.asignar_cascada`): recorre las metas por prioridad
y llena cada `monto_objetivo` antes de pasar a la siguiente. `ahorrado` por meta **NO se
guarda**: se deriva del pool. El sobrante tras cubrir todas las metas es "libre".

Cada meta puede tener **fecha objetivo opcional** (por edad `BIRTH_DATE + edad`, fecha
exacta, o **sin límite**). Semilla inicial: 🚗 carro $27.000 (prioridad 1, antes de los 30)
· 🏠 casa $100.000 (prioridad 2, antes de los 35). `BIRTH_DATE` real: **feb 1998**.

Para cada meta, con `objetivo_acumulado` = Σ montos hasta esa prioridad:

```
ahorrado         = min de lo que le tocó del pool en cascada
restante         = monto_objetivo - ahorrado
meses_estimados  = ceil((objetivo_acumulado - pool) / ahorro_mensual)   # secuencial
fecha_estimada   = hoy + meses_estimados                                 # informativa
ahorro_necesario = (objetivo_acumulado - pool) / meses_hasta(fecha_objetivo)
en_camino        = fecha_estimada <= fecha_objetivo
```

`ahorro_necesario` responde a *"para tener la casa antes de los 35 —pagando primero el
carro— tengo que ahorrar $X/mes"*. `ahorro_mensual` = promedio de profit mensual reciente.

### Sección motivadora ("¿a qué edad lo logro?")

Cada meta convierte su `fecha_estimada` en **edad** (años/meses entre `BIRTH_DATE` y la
fecha). Con fecha objetivo: 🟢 si vas en camino, 🟡/🔴 con el empujón concreto (cuánto
ahorrar/mes). Sin fecha objetivo: solo la fecha estimada según tu ritmo.

---

## 4. Simulador de cascada "¿y si ahorro más?"

Función estrella de **Predicciones**. Un aumento `Δ` de ahorro mensual se aplica a **toda
la cola** y adelanta cada meta respetando el orden:

```
meses_meta(rate) = ceil((objetivo_acumulado - pool) / rate)
base  = meses_meta(ahorro_mensual)
nueva = meses_meta(ahorro_mensual + Δ)
meses_ahorrados = base - nueva     # por cada meta de la cola
```

El dashboard muestra la línea de tiempo (carro → casa → …) con `fecha_base → fecha_nueva`
y "N meses antes" por meta, más la proyección de patrimonio con la curva extra. Cada dólar
extra mueve toda la aguja.

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
envelopes    (id, nombre, tipo[porcentaje|fijo|residual], valor, arrastre)
operaciones  (id, nombre, fecha, descripcion)            # compra que agrupa movimientos
movimientos  (id, tipo[gasto|ingreso], fecha, monto, descripcion,
              sobre, categoria,            # solo gastos
              fuente_ingreso,              # solo ingresos
              comercio, grupo_id→operaciones, creado_en)
recurrentes  (id, nombre, monto_base, iva, isd, periodicidad, sobre, categoria,
              comercio, activo)            # suscripciones para pronóstico (Shopify…)
```

**Tres dimensiones del movimiento** (gasto):
- **sobre** (presupuesto): `pareja`, `familia`, `personal`, `iglesia`, `transporte`, `ahorro`.
- **categoria** (tipo): `comida`, `hogar`, `tecnologia`, `regalo`, `salud`, `suscripcion`,
  `educacion`, `transporte`, `impuestos`, `entretenimiento`, `iglesia`, `otros`.
- **comercio** (a quién): Amazon, Shopify, Uber, Gobierno, supermercado, Iglesia…

Compras multi-costo (ej. laptop) = una `operacion` con varios `movimientos` (ítem +
impuestos + envío), cada uno con su comercio. No se registra método de pago (siempre tarjeta).
