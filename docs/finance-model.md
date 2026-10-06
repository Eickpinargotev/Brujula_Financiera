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

**Fuentes de ingreso** (en la UI: *categorías de ingreso*): `trabajo` ·
`proyecto_personal`. Viven en la tabla `income_sources` y el dueño puede
crear/renombrar/borrar las que quiera desde el dashboard; no llevan tope porque el ingreso
no se presupuesta. Renombrar una arrastra los ingresos que la usaban, y no se puede borrar
una que todavía tenga movimientos.

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
tope(sobre, mes) = % del ingreso REAL del mes  |  monto fijo
arrastre(sobre)  = Σ_meses_anteriores (tope_mes − gastado_mes)     # todo el historial
margen(sobre)    = tope + arrastre − gastado
🟢 gastado dentro del margen · 🟡 cerca del límite · 🔴 lo superó
```

**El arrastre NO se suma al tope que se muestra.** El tope es el del mes ("esto me tocaba
gastar") y el arrastre va aparte ("y además me puedo pasar esto sin problema"). Solo actúa
como colchón para el color: pasarse del tope del mes no es rojo si el arrastre lo cubre.
Y si no gastaste nada en el mes, nunca es rojo — un arrastre negativo se ve en su línea,
en rojo, pero no describe el mes en curso.

**Cómo se calcula:** mes a mes, desde el primer movimiento del historial hasta el día
anterior al mes que se muestra. La asignación de cada mes usa el **ingreso REAL de ese
mes** (10 % de $0 = $0), así que gastar sin ingresos deja el sobre en negativo y ese
negativo se arrastra. Ejemplo: junio ingresa $1000, familia (10 %) tiene $100 y gastas $50
→ julio arranca con tope $100 y **arrastre +$50**. Si en junio gastas $115, julio arranca
con **arrastre −$15**.

El arrastre aplica a **todas** las categorías con tope. Las categorías sin tope
(`valor = 0`) salen como 🔘 *libre*: no asignan ni arrastran, solo muestran lo gastado.
El bloque **Categorías sigue el periodo elegido en Resumen**, igual que los KPIs y la
distribución del gasto. Gastado incluye solo las fechas seleccionadas. Las asignaciones
se suman mes a mes: porcentajes y residual usan los ingresos dentro del rango; los topes
fijos cuentan una vez por cada mes calendario incluido, incluso si es parcial, sin
prorrateo diario. El arrastre corresponde a los meses anteriores al primer mes del rango;
no incorpora movimientos posteriores ni vuelve a contar meses incluidos en la selección.
La cabecera muestra el rango y la fecha de corte del arrastre. Sin filtro se mantiene
el último mes con datos como periodo inicial.

**Préstamos:** `prestamo` existe como categoría de ingreso y de egreso. El detalle es el
nombre de la otra persona y se normaliza (mayúsculas, espacios y tildes no importan). Los
movimientos se concilian por persona en orden `fecha + id`, aplicando cada pago al préstamo
más antiguo (FIFO):

- Si yo presto: el egreso abre una cuenta por cobrar; el ingreso posterior la salda.
- Si me prestan: el ingreso abre una cuenta por pagar; el egreso posterior la salda.
- Cada préstamo se deriva como `pendiente`, `abonado` o `pagado`; no se borra el historial.
- Un pago mayor al saldo se bloquea con un aviso; si el excedente es un nuevo préstamo,
  debe registrarse como un movimiento separado.

El KPI muestra por separado lo pendiente **por cobrar** y **por pagar**. Los estados no se
guardan: se reconstruyen desde todo el historial, así que editar o borrar una fecha/monto
recalcula automáticamente las aplicaciones posteriores.

En **Movimientos**, los préstamos se excluyen de `Todos`, `Ingresos` y `Gastos` y viven en
su sección propia. Allí se agrupan por persona: cada cuenta muestra el saldo vigente, si
es por cobrar o por pagar, y sus movimientos del periodo. Una cuenta abierta siempre se
muestra aunque el préstamo original sea anterior al rango seleccionado.

Los préstamos también quedan fuera de toda la contabilidad ordinaria del **Resumen**:
ingreso, gasto, balance, tasa de ahorro, flujo mensual, gasto por categoría, arrastres,
patrimonio y avance de metas. Son movimientos de capital, no dinero ganado ni consumido;
sus saldos se consultan exclusivamente en la sección `Préstamos`.

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
pool = Σ saldos de cuentas
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
> parámetros, metas, categorías y cuentas por defecto (idempotente). Se editan y consultan
> desde el dashboard.

```
parameters   (key, value, description)   # birth_date, base_salary, iess_personal_rate,
                                          # income_tax_monthly, extra_income_baseline,
                                          # timezone, currency
goals        (id, nombre, monto_objetivo, prioridad, emoji, edad_objetivo,
              fecha_objetivo, ahorro_mensual, creada_en)   # carro, casa (cascada)
goal_commitments (id, goal_id→goals, fecha, ahorro_mensual, ahorrado,
              meses_estimados, fecha_estimada, creado_en)  # historial del compromiso
envelopes    (id, nombre, tipo[porcentaje|fijo|residual], valor, arrastre)  # categorías de egreso
income_sources (id, nombre)                              # categorías de ingreso (sin tope)
accounts     (id, nombre, moneda, activa, creada_en)      # bancos/billeteras/exchanges
operaciones  (id, nombre, fecha, descripcion)            # compra que agrupa movimientos
movimientos  (id, tipo[gasto|ingreso], fecha, monto, descripcion,
              sobre,                       # solo gastos (única clasificación)
              fuente_ingreso,              # solo ingresos
              account_id→accounts, comercio, grupo_id→operaciones, creado_en)
account_adjustments (id, account_id→accounts, fecha, monto, descripcion, creado_en)
transfers    (id, source_account_id→accounts, destination_account_id→accounts,
              fecha, monto, descripcion, creado_en)
recurrentes  (id, nombre, monto_base, iva, isd, periodicidad, sobre,
              comercio, activo)            # suscripciones para pronóstico (Shopify…)
```

**Dos dimensiones del movimiento** (gasto):
- **sobre** (presupuesto): `pareja`, `familia`, `personal`, `iglesia`, `transporte`, `ahorro`.
- **comercio** (a quién): Amazon, Shopify, Uber, Gobierno, supermercado, Iglesia…

**Compromiso por meta:** `ahorro_mensual` fija el ritmo con el que se calcula la fecha
estimada (`meses = faltante ÷ compromiso`; sin compromiso se usa el ahorro promedio).
Cada cambio del compromiso guarda un hito en `goal_commitments` para ver cómo la fecha
objetivo fue bajando desde que se creó la meta.

Compras multi-costo (ej. laptop) = una `operacion` con varios `movimientos` (ítem +
impuestos + envío), cada uno con su comercio y cuenta. Las transferencias entre cuentas
propias se registran aparte y no modifican ingresos ni gastos.
