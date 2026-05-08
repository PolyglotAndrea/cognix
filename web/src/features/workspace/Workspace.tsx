import { useState } from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { TopBar } from './TopBar'
import { LeftPanel } from './LeftPanel'
import { CenterPanel } from './CenterPanel'
import { RightPanel } from './RightPanel'
import { cn } from '@/shared/lib/cn'

interface SortablePanelProps {
  id: string
  children: React.ReactNode
  className?: string
}

function SortablePanel({ id, children, className }: SortablePanelProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id })

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    zIndex: isDragging ? 100 : 10,
    opacity: isDragging ? 0.8 : 1,
    position: 'relative' as const,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn("flex flex-col h-full bg-background", className)}
    >
      {React.Children.map(children, child => {
        if (React.isValidElement(child)) {
          return React.cloneElement(child as React.ReactElement<any>, { 
            dragHandleProps: { ...attributes, ...listeners } 
          })
        }
        return child
      })}
    </div>
  )
}

import * as React from 'react'

export function Workspace() {
  const [items, setItems] = useState(['left', 'center', 'right'])
  
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event

    if (over && active.id !== over.id) {
      setItems((items) => {
        const oldIndex = items.indexOf(active.id as string)
        const newIndex = items.indexOf(over.id as string)
        return arrayMove(items, oldIndex, newIndex)
      })
    }
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden selection:bg-primary/20">
      <TopBar />
      
      <div className="flex-1 flex overflow-hidden relative z-0">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={items}
            strategy={horizontalListSortingStrategy}
          >
            {items.map((id) => (
              <SortablePanel 
                key={id} 
                id={id} 
                className={cn(
                  "transition-[width,flex] duration-300",
                  id === 'center' ? 'flex-1 min-w-0' : 'w-80 shrink-0'
                )}
              >
                {id === 'left' && <LeftPanel />}
                {id === 'center' && <CenterPanel />}
                {id === 'right' && <RightPanel />}
              </SortablePanel>
            ))}
          </SortableContext>
        </DndContext>
      </div>
    </div>
  )
}
