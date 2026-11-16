export function playSound(type: 'send' | 'receive') {
  try {
    const url = type === 'send' ? '/assets/frappe/sounds/submit.mp3' : '/assets/frappe/sounds/alert.mp3'
    const audio = new Audio(url)
    audio.volume = 0.3
    void audio.play().catch(() => {})
  } catch {
    // browser autoplay policy
  }
}
