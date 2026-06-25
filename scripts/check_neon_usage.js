const {Pool} = require('pg');
const pool = new Pool({connectionString:'postgresql://neondb_owner:npg_oCyB2QmlZcr4@ep-empty-frost-atrkwhof-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require'});

async function check() {
  const tables = ['personas','empresas','relaciones','etiquetas','persona_etiqueta','empresa_etiqueta','persona_empresa','auditoria','usuarios'];
  console.log('=== REGISTROS POR TABLA ===');
  for (const t of tables) {
    try {
      const r = await pool.query('SELECT COUNT(*) as cnt FROM ' + t);
      console.log('  ' + t.padEnd(20) + r.rows[0].cnt);
    } catch(e) { console.log('  ' + t.padEnd(20) + 'ERR'); }
  }

  try {
    const r = await pool.query('SELECT pg_database_size(current_database()) as bytes');
    const mb = r.rows[0].bytes / 1024 / 1024;
    const limit = 500;
    console.log('');
    console.log('=== CAPACIDAD NEON (Free Plan 500MB) ===');
    console.log('  Usado:      ' + Math.round(mb*100)/100 + ' MB');
    console.log('  Disponible: ' + Math.round((limit - mb)*100)/100 + ' MB');
    console.log('  Progreso:   ' + Math.round(mb/limit*10000)/100 + '%');
    if (mb < 100) console.log('  Estado:    ✅ Todo bien');
    else if (mb < 400) console.log('  Estado:    ⚠️  Mas de la mitad usado');
    else console.log('  Estado:    🔴 Queda poco espacio');
  } catch(e) { console.log('Error:', e.message); }

  pool.end();
}
check();
