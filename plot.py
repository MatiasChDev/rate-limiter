import datetime as dt

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np

# Create figure for plotting
fig = plt.figure()
ax = fig.add_subplot(1, 1, 1)
xs = []
ys = []


# This function is called periodically from FuncAnimation
def animate(i, xs, ys):
    # Add x and y to lists
    xs.append(dt.datetime.now().strftime("%H:%M:%S.%f"))
    ys.append(np.random.randint(0, 10))

    # Limit x and y lists to 20 items
    xs = xs[-20:]
    ys = ys[-20:]

    # Draw x and y lists
    ax.clear()
    ax.plot(xs, ys)

    # Format plot
    plt.xticks(rotation=45, ha="right")
    plt.subplots_adjust(bottom=0.30)
    plt.title("Requests por second over time")
    plt.ylabel("req/s")


# Set up plot to call animate() function periodically
ani = animation.FuncAnimation(fig, animate, fargs=(xs, ys), interval=1000)
plt.show()
