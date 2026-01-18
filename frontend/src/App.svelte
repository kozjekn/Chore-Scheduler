<script>
  import { onMount } from 'svelte';

  let email = '';
  let storedEmail = '';
  
  let groupedTasks = {}; 
  let roomOrder = [];    
  let recentHistory = [];
  let multiRoomTasks = new Set();
  
  let loading = false;
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

  onMount(() => {
    storedEmail = localStorage.getItem('chore_user_email');
    if (storedEmail) {
      email = storedEmail;
      fetchTasks();
    }
  });

  function saveEmail() {
    if (email) {
      localStorage.setItem('chore_user_email', email);
      storedEmail = email;
      fetchTasks();
    }
  }

  function logout() {
    localStorage.removeItem('chore_user_email');
    storedEmail = '';
    groupedTasks = {};
    recentHistory = [];
  }

  async function fetchTasks() {
    loading = true;
    try {
      const res = await fetch(`${API_URL}/tasks?email=${encodeURIComponent(storedEmail)}`);
      const data = await res.json();
      processTasks(data.due_tasks);
      recentHistory = data.recent_history;
    } catch (e) {
      console.error(e);
      alert("Error connecting to server");
    } finally {
      loading = false;
    }
  }

  function processTasks(tasks) {
    const groups = {};
    const taskCounts = {}; 

    tasks.forEach(t => {
      if (!groups[t.room]) groups[t.room] = [];
      groups[t.room].push(t);
      taskCounts[t.task] = (taskCounts[t.task] || 0) + 1;
    });

    multiRoomTasks = new Set();
    Object.keys(taskCounts).forEach(key => {
        if (taskCounts[key] > 1) multiRoomTasks.add(key);
    });

    for (const room in groups) {
      groups[room].sort((a, b) => a.days_until - b.days_until);
    }

    groupedTasks = groups;
    roomOrder = Object.keys(groups).sort();
  }

  async function completeTask(taskName, roomName) {
    try {
      groupedTasks[roomName] = groupedTasks[roomName].filter(t => t.task !== taskName);
      if (groupedTasks[roomName].length === 0) {
        delete groupedTasks[roomName];
        roomOrder = roomOrder.filter(r => r !== roomName);
      }
      groupedTasks = groupedTasks;

      await fetch(`${API_URL}/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: storedEmail, task_name: taskName, room_name: roomName })
      });
      fetchTasks(); 
    } catch (e) {
      alert("Failed to log task");
      fetchTasks();
    }
  }

  async function undoTask(taskName, roomName, date) {
    if(!confirm(`Uncheck "${taskName}" in ${roomName}?`)) return;
    try {
      await fetch(`${API_URL}/uncheck`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: storedEmail, task_name: taskName, room_name: roomName, date: date })
      });
      fetchTasks();
    } catch (e) {
      alert("Failed to delete log");
    }
  }
</script>

<main class="container py-4" style="max-width: 800px;">
  
  {#if !storedEmail}
    <div class="row justify-content-center mt-5">
      <div class="col-md-6">
        <div class="card shadow-sm border-0">
          <div class="card-body text-center p-5">
            <h1 class="h3 mb-4">🏠 Chore Login</h1>
            <div class="input-group mb-3">
              <input type="email" class="form-control" bind:value={email} placeholder="Enter your email">
              <button class="btn btn-primary px-4" on:click={saveEmail}>Enter</button>
            </div>
          </div>
        </div>
      </div>
    </div>

  {:else}
    <div class="d-flex justify-content-between align-items-center mb-4 border-bottom pb-3">
      <div>
        <h2 class="h4 mb-0 text-dark">Hi, {storedEmail.split('@')[0]}</h2>
        <small class="text-muted">Weekly chore tracker</small>
      </div>
      <button class="btn btn-outline-danger btn-sm" on:click={logout}>Logout</button>
    </div>

    {#if loading}
      <div class="text-center py-5">
        <div class="spinner-border text-primary" role="status"></div>
      </div>
    {:else}
      
      <h3 class="h6 mb-3 text-uppercase text-muted fw-bold tracking-wide">
        <i class="bi bi-calendar-check me-2"></i>Upcoming Chores
      </h3>

      {#if roomOrder.length === 0}
        <div class="alert alert-info border-0 text-center py-4">
          <i class="bi bi-check2-circle fs-1"></i><br>
          <strong>All done!</strong>
        </div>
      {:else}
        <div class="row g-3">
          {#each roomOrder as room}
            <div class="col-12">
              <div class="card border-0 shadow-sm">
                <div class="card-header bg-white border-bottom d-flex align-items-center py-3">
                  <span class="badge rounded-pill bg-primary me-2">{groupedTasks[room].length}</span>
                  <h5 class="mb-0 fw-bold">{room}</h5>
                </div>
                <div class="list-group list-group-flush">
                  {#each groupedTasks[room] as task}
                    <div class="list-group-item d-flex justify-content-between align-items-center p-3">
                      <div class="d-flex flex-column">
                        <div class="d-flex align-items-center gap-2">
                          <span class="fw-bold text-dark">{task.task}</span>
                          {#if multiRoomTasks.has(task.task)}
                            <i class="bi bi-layers text-primary" title="Repeated in other rooms"></i>
                          {/if}
                        </div>
                        
                        {#if task.notes}
                          <small class="text-muted fst-italic mt-1">{task.notes}</small>
                        {/if}
                        
                        <div class="mt-2 small">
                          <span class="badge {task.days_until <= 0 ? 'bg-danger' : 'bg-success'}">
                             {task.days_until <= 0 ? 'DUE NOW' : `In ${task.days_until} days`}
                          </span>
                          <span class="text-muted ms-2">Target: {task.target_day}</span>
                        </div>
                      </div>

                      <button 
                        class="btn btn-success rounded-circle shadow-sm" 
                        style="width: 45px; height: 45px;"
                        on:click={() => completeTask(task.task, task.room)}
                      >
                        <i class="bi bi-check-lg"></i>
                      </button>
                    </div>
                  {/each}
                </div>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <div class="mt-5 pt-4 border-top">
        <h3 class="h6 mb-3 text-uppercase text-muted fw-bold">
          <i class="bi bi-history me-2"></i>Recently Done
        </h3>
        
        {#if recentHistory.length > 0}
          <div class="list-group">
            {#each recentHistory as log}
              <div class="list-group-item bg-light d-flex justify-content-between align-items-center border-0 mb-2 rounded shadow-sm">
                <div>
                  <div class="text-muted text-decoration-line-through">{log.task}</div>
                  <small class="text-secondary">{log.room} • {log.date}</small>
                </div>
                <button class="btn btn-danger text-decoration-none" on:click={() => undoTask(log.task, log.room, log.date)}>
                  Undo
                </button>
              </div>
            {/each}
          </div>
        {/if}
      </div> 

    {/if}
  {/if}
</main>

<style>
  .tracking-wide { letter-spacing: 0.05em; }
  .list-group-item { transition: background 0.2s; }
  .list-group-item:hover { background-color: #fcfcfc; }
</style>