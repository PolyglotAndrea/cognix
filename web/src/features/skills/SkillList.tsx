import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { Puzzle, Download } from 'lucide-react'

export default function SkillList() {
  const { data: skills, isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: () => api.get('/skills').then((r) => r.data).catch(() => []),
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Skills</h2>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : skills?.length ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {skills.map((skill: any) => (
            <div key={skill.name} className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                    <Puzzle className="w-5 h-5 text-purple-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{skill.name}</h3>
                    <p className="text-sm text-gray-500">v{skill.version}</p>
                  </div>
                </div>
              </div>
              <p className="text-sm text-gray-600 mb-4">{skill.description || 'No description'}</p>
              {skill.tags && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {skill.tags.split(',').map((tag: string) => (
                    <span key={tag} className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs">
                      {tag.trim()}
                    </span>
                  ))}
                </div>
              )}
              <button className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-50 text-purple-600 rounded-lg hover:bg-purple-100 transition-colors text-sm">
                <Download className="w-4 h-4" />
                Install
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 bg-white rounded-xl border border-gray-100">
          <Puzzle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No skills installed</p>
        </div>
      )}
    </div>
  )
}
